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


def _issue9_rule_ids() -> tuple[str, ...]:
    counts = {1: 14, 2: 2, 3: 7, 4: 5, 5: 5, 6: 6, 7: 3, 8: 7, 9: 4}
    numbered = [
        f"{section}.{number}" for section, count in counts.items() for number in range(1, count + 1)
    ]
    return tuple(numbered + [f"GR-{number}" for number in range(1, 9)])


def make_standard_pack(root: Path, *, review_state: ReviewState = ReviewState.REVIEWED) -> Path:
    root.mkdir()
    rules = [
        RuleRecord(
            rule_id=rule_id,
            requirement=(
                "Use approved words or technical terms."
                if rule_id == "1.1"
                else "Do not use semicolons."
                if rule_id == "8.1"
                else f"Reviewed requirement for {rule_id}."
            ),
            treatment=(
                RuleTreatment.DETERMINISTIC if rule_id in {"1.1", "8.1"} else RuleTreatment.LEARNED
            ),
            review_state=review_state,
            source=_source(),
        )
        for rule_id in _issue9_rule_ids()
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
    dictionary.extend(
        DictionaryEntry(
            entry_id=f"approved-{index:04d}",
            word=f"approvedword{index}",
            status="approved",
            parts_of_speech=("noun",),
            review_state=review_state,
            source=_source(),
        )
        for index in range(873)
    )
    dictionary.extend(
        DictionaryEntry(
            entry_id=f"unapproved-{index:04d}",
            word=f"blockedword{index}",
            status="unapproved",
            parts_of_speech=("noun",),
            alternatives=("approvedword0",),
            review_state=review_state,
            source=_source(),
        )
        for index in range(1273)
    )
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
            rule_id=rule.rule_id,
            deterministic_checkers=(
                ("vocabulary",)
                if rule.rule_id == "1.1"
                else ("semicolon",)
                if rule.rule_id == "8.1"
                else ()
            ),
            coverage_scope=(
                "full" if rule.rule_id == "8.1" else "partial" if rule.rule_id == "1.1" else "none"
            ),
            release_gate="blocking" if rule.rule_id == "8.1" else "report_only",
            reason="Punctuation is conclusive."
            if rule.rule_id == "8.1"
            else "Context review is required.",
        )
        for rule in rules
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
            numbered_rules=53,
            general_rules=8,
            approved_words=875,
            unapproved_words=1274,
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
