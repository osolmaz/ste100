from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import make_standard_pack
from ste100.extract import (
    build_conformance_matrix,
    extract_dictionary_candidates,
    extract_rule_candidates,
    extraction_audit,
    write_draft_extraction,
)
from ste100.models import ReviewState, StandardManifest
from ste100.schemas import generate_schemas
from ste100.standard import StandardValidationError, load_standard_pack, validate_standard_pack

_SOURCE = Path("docs/ASD-STE100_ISSUE9.txt")


def test_issue9_rule_extraction_has_complete_stable_catalog() -> None:
    text = _SOURCE.read_text(encoding="utf-8")
    rules = extract_rule_candidates(text, source_name=str(_SOURCE))

    assert len(rules) == 61
    assert sum(not rule.rule_id.startswith("GR-") for rule in rules) == 53
    assert sum(rule.rule_id.startswith("GR-") for rule in rules) == 8
    assert rules[0].rule_id == "1.1"
    assert rules[0].requirement.endswith("Technical verbs.")
    assert rules[-1].rule_id == "GR-8"
    assert rules[-1].requirement == "Possessive form"
    assert len(build_conformance_matrix(rules)) == 61


def test_dictionary_extraction_is_explicitly_a_non_runtime_draft() -> None:
    text = _SOURCE.read_text(encoding="utf-8")
    rules = extract_rule_candidates(text, source_name=str(_SOURCE))
    candidates = extract_dictionary_candidates(text, source_name=str(_SOURCE))
    audit = extraction_audit(rules, candidates)

    assert audit["counts_match"] is False
    assert audit["runtime_eligible"] is False
    assert audit["candidate_counts"] == {
        "numbered_rules": 53,
        "general_rules": 8,
        "approved_words": 876,
        "unapproved_words": 1318,
    }
    assert all(candidate.review_state is ReviewState.DRAFT for candidate in candidates)


def test_draft_writer_emits_all_auditable_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "draft"
    audit = write_draft_extraction(_SOURCE, output)
    assert audit["runtime_eligible"] is False
    assert {path.name for path in output.iterdir()} == {
        "rules.json",
        "dictionary-candidates.json",
        "conformance.json",
        "extraction-audit.json",
    }
    assert json.loads((output / "extraction-audit.json").read_text())["counts_match"] is False


def test_reviewed_standard_pack_loads_and_indexes_forms(tmp_path: Path) -> None:
    pack = load_standard_pack(make_standard_pack(tmp_path / "pack"))
    assert pack.manifest.issue == 9
    assert pack.dictionary_by_word["installed"][0].word == "install"
    assert pack.rules_by_id["8.1"].requirement == "Do not use semicolons."


def test_invalid_manifest_is_reported_without_loading_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    root.mkdir()
    (root / "standard.json").write_text("{bad json", encoding="utf-8")
    report = validate_standard_pack(root)
    assert not report.valid
    assert [issue.code for issue in report.issues] == ["invalid_manifest"]


def test_digest_mismatch_prevents_loading(tmp_path: Path) -> None:
    root = make_standard_pack(tmp_path / "pack")
    (root / "rules.json").write_text("[]\n", encoding="utf-8")
    report = validate_standard_pack(root)

    assert not report.valid
    assert "digest_mismatch" in {issue.code for issue in report.issues}
    try:
        load_standard_pack(root)
    except StandardValidationError as error:
        assert error.report == report
    else:
        raise AssertionError("invalid pack loaded")


def test_draft_pack_requires_explicit_validation_opt_in_and_never_loads(tmp_path: Path) -> None:
    root = make_standard_pack(tmp_path / "pack", review_state=ReviewState.DRAFT)
    assert not validate_standard_pack(root).valid
    assert validate_standard_pack(root, allow_draft=True).valid
    with pytest.raises(StandardValidationError, match="draft_pack"):
        load_standard_pack(root)


def test_issue_and_expected_counts_are_fixed_to_issue9(tmp_path: Path) -> None:
    root = make_standard_pack(tmp_path / "pack")
    manifest_path = root / "standard.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expected_counts"]["approved_words"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = validate_standard_pack(root)
    assert "invalid_expected_counts" in {issue.code for issue in report.issues}

    manifest["issue"] = 10
    with pytest.raises(ValidationError):
        StandardManifest.model_validate(manifest)


def test_artifact_path_cannot_escape_pack(tmp_path: Path) -> None:
    root = make_standard_pack(tmp_path / "pack")
    outside = tmp_path / "outside.json"
    outside.write_text("[]\n", encoding="utf-8")
    manifest_path = root / "standard.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = manifest["file_digests"].pop("rules.json")
    manifest["file_digests"]["../outside.json"] = digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_standard_pack(root)
    assert not report.valid
    assert "unsafe_artifact_path" in {issue.code for issue in report.issues}


def test_checked_in_json_schemas_are_reproducible(tmp_path: Path) -> None:
    generated = generate_schemas(tmp_path)
    assert {path.name for path in generated} == {path.name for path in Path("schemas").iterdir()}
    for path in generated:
        assert path.read_bytes() == (Path("schemas") / path.name).read_bytes()
