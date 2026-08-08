from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import make_standard_pack
from ste100.curate import write_runtime_pack
from ste100.extract import extract_rule_candidates
from ste100.models import StandardManifest
from ste100.schemas import generate_schemas
from ste100.standard import (
    StandardValidationError,
    bundled_standard_path,
    load_bundled_standard,
    load_standard_pack,
    validate_standard_pack,
)

_SOURCE = Path("docs/ASD-STE100_ISSUE9.txt")


def _refresh_digest(root: Path, name: str) -> None:
    manifest_path = root / "standard.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
    manifest["file_digests"][name] = f"sha256:{digest}"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_issue9_rule_extraction_has_complete_source_catalog() -> None:
    rules = extract_rule_candidates(_SOURCE.read_text(encoding="utf-8"), source_name=str(_SOURCE))
    assert len(rules) == 61
    assert sum(not rule.rule_id.startswith("GR-") for rule in rules) == 53
    assert sum(rule.rule_id.startswith("GR-") for rule in rules) == 8
    assert rules[0].rule_id == "1.1"
    assert rules[0].requirement.endswith("Technical verbs.")
    assert rules[-1].rule_id == "GR-8"
    assert rules[-1].requirement == "Possessive form"
    encoded = json.dumps([rule.model_dump(mode="json") for rule in rules])
    assert "review" not in encoded
    assert "coverage" not in encoded


def test_standard_pack_loads_and_indexes_forms(tmp_path: Path) -> None:
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
    with pytest.raises(StandardValidationError):
        load_standard_pack(root)


def test_removed_artifacts_are_rejected(tmp_path: Path) -> None:
    root = make_standard_pack(tmp_path / "pack")
    (root / "coverage.json").write_text("[]\n", encoding="utf-8")
    manifest_path = root / "standard.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["file_digests"]["coverage.json"] = (
        "sha256:" + hashlib.sha256((root / "coverage.json").read_bytes()).hexdigest()
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = validate_standard_pack(root)
    assert "artifact_set" in {issue.code for issue in report.issues}


def test_qualifier_and_pos_order_do_not_make_a_duplicate_key_valid(tmp_path: Path) -> None:
    root = make_standard_pack(tmp_path / "pack")
    dictionary_path = root / "dictionary.json"
    dictionary = json.loads(dictionary_path.read_text(encoding="utf-8"))
    dictionary[0]["parts_of_speech"] = ["verb", "noun"]
    duplicate = dict(dictionary[0])
    duplicate["entry_id"] = "install-v-qualified"
    duplicate["qualifier"] = "install in"
    duplicate["parts_of_speech"] = ["noun", "verb"]
    dictionary.append(duplicate)
    dictionary_path.write_text(json.dumps(dictionary, indent=2) + "\n", encoding="utf-8")
    _refresh_digest(root, "dictionary.json")
    report = validate_standard_pack(root)
    assert any(
        issue.code == "duplicate_id" and "status/headword/part-of-speech" in issue.message
        for issue in report.issues
    )


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
    assert len(pack.dictionary) == 2193
    assert set(pack.manifest.file_digests) == {"rules.json", "dictionary.json"}
    assert all(entry.source.page is not None for entry in pack.dictionary)
    encoded = json.dumps(pack.manifest.model_dump(mode="json"))
    assert "review" not in encoded
    assert "coverage" not in encoded
    assert "published_counts" not in encoded


def test_bundled_dictionary_has_unique_ids_and_status_pos_keys() -> None:
    dictionary = load_bundled_standard().dictionary
    assert len({entry.entry_id for entry in dictionary}) == len(dictionary)
    keys = {
        (entry.word.casefold(), entry.status, tuple(sorted(set(entry.parts_of_speech))))
        for entry in dictionary
    }
    assert len(keys) == len(dictionary)
    assert all(entry.word == entry.word.casefold() for entry in dictionary)
    assert all(entry.parts_of_speech for entry in dictionary)


def test_wrapped_dictionary_headwords_do_not_include_column_bleed() -> None:
    dictionary = load_bundled_standard().dictionary
    by_word = {entry.word: entry for entry in dictionary}
    assert by_word["electronically"].status == "approved"
    assert by_word["longitudinally"].status == "approved"
    assert by_word["precautionary"].status == "unapproved"
    assert any(entry.word == "heat" and entry.status == "approved" for entry in dictionary)
    assert not {
        "electronically rela",
        "longitudinally in a",
        "precautionary p",
        "heard heat",
        "long no longer",
    } & set(by_word)
    assert any(entry.word == "long" and entry.qualifier == "no longer" for entry in dictionary)


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


def test_every_bundled_dictionary_entry_is_indexed() -> None:
    pack = load_bundled_standard()
    index = pack.dictionary_by_word
    for entry in pack.dictionary:
        expressions = (
            (entry.qualifier,)
            if entry.qualifier is not None
            else (entry.word, *entry.approved_forms)
        )
        for expression in expressions:
            assert entry in index[expression.casefold()]


def test_standard_pack_requires_canonical_issue9_rule_ids(tmp_path: Path) -> None:
    root = make_standard_pack(tmp_path / "pack")
    rules_path = root / "rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rules[-1]["rule_id"] = "GR-9"
    rules_path.write_text(json.dumps(rules), encoding="utf-8")
    _refresh_digest(root, "rules.json")
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
    assert "unsafe_artifact_path" in {issue.code for issue in report.issues}


def test_standard_manifest_rejects_other_issues() -> None:
    manifest = load_bundled_standard().manifest.model_dump(mode="json")
    manifest["issue"] = 10
    with pytest.raises(ValidationError):
        StandardManifest.model_validate(manifest)


def test_checked_in_json_schemas_are_reproducible(tmp_path: Path) -> None:
    generated = generate_schemas(tmp_path)
    assert {path.name for path in generated} == {path.name for path in Path("schemas").iterdir()}
    for path in generated:
        assert path.read_bytes() == (Path("schemas") / path.name).read_bytes()
