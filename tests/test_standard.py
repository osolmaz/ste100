from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import make_standard_pack
from ste100.checker import analyze
from ste100.curate import write_runtime_pack
from ste100.extract import extract_rule_candidates
from ste100.models import FindingKind, ReviewState, StandardManifest
from ste100.schemas import generate_schemas
from ste100.standard import (
    StandardValidationError,
    bundled_standard_path,
    load_bundled_standard,
    load_standard_pack,
    validate_standard_pack,
)

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
    assert all(rule.review_state is ReviewState.DRAFT for rule in rules)


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


def test_manifest_counts_must_match_artifacts_and_published_differences_warn(
    tmp_path: Path,
) -> None:
    root = make_standard_pack(tmp_path / "pack")
    manifest_path = root / "standard.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expected_counts"]["approved_words"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = validate_standard_pack(root)
    codes = {issue.code for issue in report.issues}
    assert "count_mismatch" in codes
    assert "published_count_difference" in codes

    manifest["published_counts"]["unapproved_words"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = validate_standard_pack(root)
    assert "invalid_published_counts" in {issue.code for issue in report.issues}

    manifest["issue"] = 10
    with pytest.raises(ValidationError):
        StandardManifest.model_validate(manifest)


def test_bundled_runtime_pack_is_reproducible(tmp_path: Path) -> None:
    output = tmp_path / "issue9"
    write_runtime_pack(_SOURCE, output)
    bundled = bundled_standard_path()
    assert {path.name for path in output.iterdir()} == {path.name for path in bundled.iterdir()}
    for path in output.iterdir():
        assert path.read_bytes() == (bundled / path.name).read_bytes()


def test_bundled_runtime_pack_is_valid_and_source_traceable() -> None:
    pack = load_bundled_standard()
    report = validate_standard_pack(bundled_standard_path())
    assert report.valid
    assert len(pack.rules) == 61
    assert len(pack.conformance) == 61
    assert len(pack.examples) >= 15
    assert sum(entry.status == "approved" for entry in pack.dictionary) == 876
    assert sum(entry.status == "unapproved" for entry in pack.dictionary) == 1320
    assert pack.manifest.published_counts.approved_words == 875
    assert pack.manifest.published_counts.unapproved_words == 1274
    assert "All source-traceable rows are retained" in pack.manifest.count_reconciliation
    assert all(entry.review_state is ReviewState.REVIEWED for entry in pack.dictionary)
    assert all(entry.source.page is not None for entry in pack.dictionary)
    warning = next(issue for issue in report.issues if issue.code == "published_count_difference")
    assert warning.severity == "warning"


def test_bundled_dictionary_has_unique_ids_and_status_pos_keys() -> None:
    dictionary = load_bundled_standard().dictionary
    assert len({entry.entry_id for entry in dictionary}) == len(dictionary)
    keys = {(entry.word.casefold(), entry.status, entry.parts_of_speech) for entry in dictionary}
    assert len(keys) == len(dictionary)
    assert all(entry.word == entry.word.casefold() for entry in dictionary)
    assert all(entry.parts_of_speech for entry in dictionary)
    assert all(not entry.approved_meanings for entry in dictionary if entry.status == "approved")


def test_bundled_approved_forms_preserve_delimiters_and_hyphens() -> None:
    index = load_bundled_standard().dictionary_by_word
    deep = next(
        entry
        for entry in index["deep"]
        if entry.status == "approved" and "adjective" in entry.parts_of_speech
    )
    de_energize = next(
        entry
        for entry in index["de-energize"]
        if entry.status == "approved" and "verb" in entry.parts_of_speech
    )
    assert {"deeper", "deepest"} <= set(deep.approved_forms)
    assert "de-energizes" in de_energize.approved_forms
    assert all(not form.startswith("(") and not form.endswith(")") for form in deep.approved_forms)


def test_bundled_deterministic_examples_match_their_labels() -> None:
    examples = load_bundled_standard().examples
    separately_tested_rules = {"5.5", "GR-1", "GR-6", "GR-7"}
    for example in examples:
        rule_id = example.rule_ids[0]
        if rule_id in separately_tested_rules:
            continue
        failed = {
            finding.rule_id
            for finding in analyze(example.text).findings
            if finding.kind is FindingKind.VIOLATION
        }
        if example.label == "negative":
            assert rule_id in failed, example.example_id
        elif example.label == "positive":
            assert rule_id not in failed, example.example_id


def test_every_bundled_dictionary_entry_is_indexed() -> None:
    pack = load_bundled_standard()
    index = pack.dictionary_by_word
    for entry in pack.dictionary:
        assert entry in index[entry.word.casefold()]
        for form in entry.approved_forms:
            assert entry in index[form.casefold()]


def test_standard_pack_requires_canonical_issue9_rule_ids(tmp_path: Path) -> None:
    root = make_standard_pack(tmp_path / "pack")
    rules_path = root / "rules.json"
    conformance_path = root / "conformance.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    conformance = json.loads(conformance_path.read_text(encoding="utf-8"))
    rules[-1]["rule_id"] = "GR-9"
    conformance[-1]["rule_id"] = "GR-9"
    rules_path.write_text(json.dumps(rules), encoding="utf-8")
    conformance_path.write_text(json.dumps(conformance), encoding="utf-8")

    manifest_path = root / "standard.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in ("rules.json", "conformance.json"):
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        manifest["file_digests"][name] = f"sha256:{digest}"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_standard_pack(root)
    assert "rule_catalog" in {issue.code for issue in report.issues}


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
