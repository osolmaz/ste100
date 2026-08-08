from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ste100.checker import analyze
from ste100.linguistics import SpacyAnalyzer
from ste100.models import FindingKind

_SPACY = SpacyAnalyzer()


def _fixtures() -> list[dict[str, object]]:
    value = json.loads(
        Path("tests/fixtures/sanitized-response-style.json").read_text(encoding="utf-8")
    )
    return cast(list[dict[str, object]], value)


def _reported_rules(text: str, *, with_spacy: bool = False) -> set[str]:
    analyzer = _SPACY if with_spacy else None
    return {finding.rule_id for finding in analyze(text, linguistic_analyzer=analyzer).findings}


def _failed_rules(text: str) -> set[str]:
    return {
        finding.rule_id
        for finding in analyze(text).findings
        if finding.kind is FindingKind.VIOLATION
    }


def test_sanitized_response_style_fixture_is_broad_and_contains_no_provenance() -> None:
    records = _fixtures()
    assert len(records) >= 15
    assert all(record["synthetic"] is True for record in records)
    forbidden = {"session_id", "source_location", "timestamp", "model", "source_agent"}
    assert all(not (forbidden & set(record)) for record in records)


def test_sanitized_rule_repairs_remove_the_expected_mechanical_failure() -> None:
    checked = 0
    for record in _fixtures():
        expected = set(cast(list[str], record["expected_changed_rule_ids"]))
        if not expected:
            continue
        initial = str(record["initial_assistant_response"])
        final = str(record["final_assistant_response"])
        observed = (
            _reported_rules(initial, with_spacy="GR-1" in expected)
            if expected <= {"GR-1", "GR-6", "GR-7"}
            else _failed_rules(initial)
        )
        assert expected <= observed, record["fixture_id"]
        assert not (expected & _reported_rules(final)), record["fixture_id"]
        checked += 1
    assert checked >= 12


def test_plain_shortening_remains_separate_from_rule_compliance() -> None:
    record = _fixtures()[0]
    initial = str(record["initial_assistant_response"])
    final = str(record["final_assistant_response"])
    assert len(final.split()) < len(initial.split())
    assert record["expected_changed_rule_ids"] == []


def test_sanitized_protected_values_are_preserved() -> None:
    record = next(
        item for item in _fixtures() if item["fixture_id"] == "sanitized-protected-values"
    )
    for value in ("UNIT_A", "28 V DC", "https://example.test/a", "`mode=2`"):
        assert value in str(record["initial_assistant_response"])
        assert value in str(record["final_assistant_response"])
