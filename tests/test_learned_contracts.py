from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import ValidationError

from ste100.bootstrap import weak_annotations
from ste100.contracts import StaticRewriter
from ste100.model_release import validate_model_release
from ste100.models import Finding, ModelManifest
from ste100.protection import protect_text
from ste100.rewrite import rewrite_candidate


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class _CapturingRewriter:
    model_id: str
    candidate: str
    seen_findings: tuple[Finding, ...] = ()

    def rewrite(self, masked_text: str, findings: tuple[Finding, ...]) -> str:
        del masked_text
        self.seen_findings = findings
        return self.candidate


def test_rewriter_hints_default_to_disabled() -> None:
    text = "Don't set UNIT_A now."
    protected = protect_text(text)
    unhinted = _CapturingRewriter(model_id="unhinted", candidate=protected.masked_text)
    rewrite_candidate(text, rewriter=unhinted)
    assert unhinted.seen_findings == ()

    hinted = _CapturingRewriter(model_id="hinted", candidate=protected.masked_text)
    rewrite_candidate(text, rewriter=hinted, use_detector_hints=True)
    assert any(finding.rule_id == "4.2" for finding in hinted.seen_findings)


def test_rewriter_output_is_untrusted_protected_and_rechecked() -> None:
    text = "Don't set UNIT_A now."
    protected = protect_text(text)
    candidate = protected.masked_text.replace("Don't", "Do not")
    outcome = rewrite_candidate(
        text,
        rewriter=StaticRewriter(model_id="rewriter-test", candidate=candidate),
    )

    assert outcome.candidate == "Do not set UNIT_A now."
    assert outcome.deterministic_gate_passed
    assert outcome.official_compliance_claimed is False
    assert all(finding.rule_id != "4.2" for finding in outcome.candidate_analysis.findings)


def test_rewriter_gate_rejects_new_deterministic_violation() -> None:
    text = "Set UNIT_A now."
    protected = protect_text(text)
    candidate = protected.masked_text.replace(" now.", "; continue.")
    outcome = rewrite_candidate(
        text,
        rewriter=StaticRewriter(model_id="rewriter-test", candidate=candidate),
    )
    assert not outcome.deterministic_gate_passed


def test_rewriter_gate_counts_duplicate_deterministic_violations() -> None:
    text = "Set UNIT_A; continue."
    protected = protect_text(text)
    candidate = protected.masked_text.replace(" continue.", " continue; stop.")
    outcome = rewrite_candidate(
        text,
        rewriter=StaticRewriter(model_id="rewriter-test", candidate=candidate),
    )
    assert not outcome.deterministic_gate_passed


def test_model_releases_have_role_specific_evidence_and_independent_roles(tmp_path: Path) -> None:
    artifact = tmp_path / "model.bin"
    evaluation = tmp_path / "evaluation.json"
    artifact.write_bytes(b"model")
    evaluation.write_text("{}", encoding="utf-8")
    manifest = ModelManifest(
        format_version="1",
        model_id="ste100-detector-small",
        role="detector",
        release="1.0.0",
        artifact_digest=_digest(artifact),
        evaluation_digest=_digest(evaluation),
        standard_issue=9,
        base_model_id="example/base",
        base_model_revision="abc123",
        pretraining_contamination="unknown",
        dataset_digests=("sha256:" + "2" * 64,),
        thresholds={"rule_macro_f1": 0.8, "span_f1": 0.7, "calibration_error": 0.1},
        protected_content_gate=False,
        span_release_gate="report_only",
        detector_hints_used=False,
    )
    report = validate_model_release(manifest, artifact=artifact, evaluation=evaluation)

    assert report.valid
    assert [issue.severity for issue in report.issues] == ["warning"]


def test_model_release_rejects_missing_files_and_thresholds(tmp_path: Path) -> None:
    manifest = ModelManifest(
        format_version="1",
        model_id="detector",
        role="detector",
        release="1.0.0",
        artifact_digest="sha256:" + "1" * 64,
        evaluation_digest="sha256:" + "2" * 64,
        standard_issue=9,
        base_model_id="base",
        base_model_revision="revision",
        pretraining_contamination="known_present",
        dataset_digests=("sha256:" + "3" * 64,),
        thresholds={},
        protected_content_gate=False,
        span_release_gate="report_only",
        detector_hints_used=False,
    )
    report = validate_model_release(
        manifest,
        artifact=tmp_path / "missing-model",
        evaluation=tmp_path / "missing-evaluation",
    )
    assert not report.valid
    assert [issue.code for issue in report.issues] == [
        "missing_release_file",
        "missing_release_file",
        "release_thresholds",
    ]


def test_rewriter_manifest_requires_protection_and_data() -> None:
    common = {
        "format_version": "1",
        "model_id": "rewriter",
        "role": "rewriter",
        "release": "1.0.0",
        "artifact_digest": "sha256:" + "1" * 64,
        "evaluation_digest": "sha256:" + "2" * 64,
        "standard_issue": 9,
        "base_model_id": "base",
        "base_model_revision": "revision",
        "pretraining_contamination": "known_absent",
        "dataset_digests": [],
        "thresholds": {},
        "protected_content_gate": False,
        "span_release_gate": "report_only",
        "detector_hints_used": True,
    }
    with pytest.raises(ValidationError):
        ModelManifest.model_validate(common)


@dataclass
class _Token:
    text: str
    idx: int
    dep_: str
    tag_: str


class _Pipeline:
    def __call__(self, text: str) -> tuple[_Token, ...]:
        del text
        return (
            _Token(text="was", idx=9, dep_="auxpass", tag_="VBD"),
            _Token(text="running", idx=13, dep_="ROOT", tag_="VBG"),
        )


def test_missing_spacy_extra_has_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from ste100.bootstrap import load_spacy_pipeline

    monkeypatch.setitem(sys.modules, "spacy", None)
    with pytest.raises(RuntimeError, match=r"ste100\[spacy\]"):
        load_spacy_pipeline("model-that-does-not-exist")


def test_spacy_bootstrap_annotations_remain_uncertain() -> None:
    annotations = weak_annotations("The unit was running.", _Pipeline())
    assert [(item.rule_id, item.label) for item in annotations] == [
        ("3.6", "uncertain"),
        ("3.5", "uncertain"),
    ]
    assert {item.annotator for item in annotations} == {"spacy_weak_bootstrap"}
