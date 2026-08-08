from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import BaseModel

from ste100.models import (
    ConformanceRecord,
    DictionaryEntry,
    DictionaryMeaning,
    ExpectedCounts,
    ReviewState,
    RuleRecord,
    RuleTreatment,
    SourceLocation,
    StandardExample,
    StandardManifest,
)
from ste100.standard import StandardPack, load_standard_pack

SOURCE_DIGEST = "sha256:" + "0" * 64


def _source(page: int = 1) -> SourceLocation:
    return SourceLocation(
        source_file="ASD-STE100_ISSUE9.txt",
        page=page,
        source_digest=SOURCE_DIGEST,
    )


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def make_standard_pack(root: Path, *, review_state: ReviewState = ReviewState.REVIEWED) -> Path:
    root.mkdir()
    rules = [
        RuleRecord(
            rule_id="1.1",
            requirement="Use approved words or technical terms.",
            treatment=RuleTreatment.DETERMINISTIC,
            review_state=review_state,
            source=_source(),
        ),
        RuleRecord(
            rule_id="8.1",
            requirement="Do not use semicolons.",
            treatment=RuleTreatment.DETERMINISTIC,
            review_state=review_state,
            source=_source(),
        ),
    ]
    dictionary = [
        DictionaryEntry(
            entry_id="install-v",
            word="install",
            status="approved",
            parts_of_speech=("verb",),
            approved_meanings=(
                DictionaryMeaning(
                    meaning_id="install-v-1", text="Put into position", rule_ids=("1.1",)
                ),
            ),
            approved_forms=("installs", "installed"),
            review_state=review_state,
            source=_source(),
        ),
        DictionaryEntry(
            entry_id="the-art",
            word="the",
            status="approved",
            parts_of_speech=("article",),
            review_state=review_state,
            source=_source(),
        ),
        DictionaryEntry(
            entry_id="utilize-v",
            word="utilize",
            status="unapproved",
            parts_of_speech=("verb",),
            alternatives=("use",),
            review_state=review_state,
            source=_source(),
        ),
    ]
    examples = [
        StandardExample(
            example_id="example-install",
            rule_ids=("1.1",),
            text="INSTALL THE UNIT.",
            label="positive",
            review_state=review_state,
            source=_source(),
        )
    ]
    conformance = [
        ConformanceRecord(
            rule_id="1.1",
            deterministic_checkers=("vocabulary",),
            coverage_scope="partial",
            release_gate="report_only",
            reason="Meanings still need context.",
        ),
        ConformanceRecord(
            rule_id="8.1",
            deterministic_checkers=("semicolon",),
            coverage_scope="full",
            release_gate="blocking",
            reason="Punctuation is conclusive.",
        ),
    ]
    files: dict[str, Sequence[BaseModel]] = {
        "rules.json": rules,
        "dictionary.json": dictionary,
        "examples.json": examples,
        "conformance.json": conformance,
    }
    for name, records in files.items():
        (root / name).write_text(
            json.dumps([record.model_dump(mode="json") for record in records], indent=2) + "\n",
            encoding="utf-8",
        )
    manifest = StandardManifest(
        format_version="1",
        standard_id="ASD-STE100",
        issue=9,
        review_state=review_state,
        source=_source(),
        expected_counts=ExpectedCounts(
            numbered_rules=2,
            general_rules=0,
            approved_words=2,
            unapproved_words=1,
        ),
        file_digests={name: _digest(root / name) for name in files},
    )
    (root / "standard.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def standard_pack(tmp_path: Path) -> StandardPack:
    return load_standard_pack(make_standard_pack(tmp_path / "standard"))
