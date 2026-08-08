"""Deterministic draft extraction from the exact Issue 9 text export."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from ste100.models import (
    ConformanceRecord,
    DictionaryCandidate,
    ReviewState,
    RuleRecord,
    RuleTreatment,
    SourceLocation,
)

_EXPECTED = {
    "numbered_rules": 53,
    "general_rules": 8,
    "approved_words": 875,
    "unapproved_words": 1274,
}
_RULE_RE = re.compile(r"^\s*Rule\s+(\d+\.\d+)\s+(.*\S)\s*$")
_GENERAL_RE = re.compile(
    r"^[ \t]*(GR-[1-8])[ \t]+(.+?)(?:[ \t]{2,}|$)",
    re.MULTILINE,
)
_POS_RE = re.compile(
    r"\((?:n|v|adj|adv|prep|pron|conj|art|aux|modal|det|number|prefix|suffix|symbol)"
    r"(?:[^)]*)\)",
    re.IGNORECASE,
)
_CONTEXTUAL_RULES = frozenset(
    {
        "1.2",
        "1.3",
        "1.4",
        "1.5",
        "1.6",
        "1.7",
        "1.8",
        "1.9",
        "1.10",
        "1.11",
        "1.12",
        "1.13",
        "1.14",
        "2.1",
        "2.2",
        "3.1",
        "3.2",
        "3.3",
        "3.4",
        "3.5",
        "3.6",
        "3.7",
        "4.1",
        "4.3",
        "4.4",
        "4.5",
        "5.2",
        "5.3",
        "5.4",
        "5.5",
        "6.1",
        "6.2",
        "6.4",
        "6.5",
        "7.1",
        "7.2",
        "7.3",
        "8.2",
        "8.3",
        "9.1",
        "9.2",
        "9.3",
        "9.4",
        "GR-1",
        "GR-2",
        "GR-3",
        "GR-4",
        "GR-5",
        "GR-6",
        "GR-7",
        "GR-8",
    }
)
_CHECKERS_BY_RULE = {
    "1.1": ("vocabulary",),
    "4.2": ("contraction",),
    "5.1": ("procedure_sentence_length",),
    "6.3": ("descriptive_sentence_length",),
    "6.6": ("paragraph_sentence_count",),
    "8.1": ("semicolon",),
    "8.4": ("word_count",),
    "8.5": ("word_count",),
    "8.6": ("word_count",),
    "8.7": ("word_count",),
}
_FULL_RULES = frozenset({"6.6", "8.1", "8.4", "8.5", "8.7"})


def sha256_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _source_location(source_name: str, digest: str, page: int) -> SourceLocation:
    return SourceLocation(source_file=source_name, page=page, source_digest=digest)


def _treatment(rule_id: str) -> RuleTreatment:
    if rule_id in _CHECKERS_BY_RULE:
        return RuleTreatment.DETERMINISTIC
    if rule_id in _CONTEXTUAL_RULES:
        return RuleTreatment.LEARNED
    return RuleTreatment.HUMAN_REVIEW


def _flush_rule(
    records: dict[str, RuleRecord],
    rule_id: str | None,
    fragments: list[str],
    source_name: str,
    digest: str,
    page: int,
) -> None:
    if rule_id is None or rule_id in records:
        return
    requirement = " ".join(fragment.strip() for fragment in fragments if fragment.strip())
    records[rule_id] = RuleRecord(
        rule_id=rule_id,
        requirement=requirement,
        treatment=_treatment(rule_id),
        review_state=ReviewState.DRAFT,
        source=_source_location(source_name, digest, page),
        notes="Extracted from the section summary; human row review is required.",
    )


def _numbered_summary_records(
    page: str,
    *,
    page_number: int,
    source_name: str,
    digest: str,
) -> tuple[RuleRecord, ...]:
    lines = page.splitlines()
    summary = next(index for index, line in enumerate(lines) if "Summary of the rules" in line)
    matches = [
        (index, match)
        for index, line in enumerate(lines[summary + 1 :], summary + 1)
        if (match := _RULE_RE.match(line)) is not None
    ]
    unique: list[tuple[int, re.Match[str]]] = []
    seen: set[str] = set()
    for item in matches:
        rule_id = item[1].group(1)
        if rule_id in seen:
            break
        seen.add(rule_id)
        unique.append(item)
    records: list[RuleRecord] = []
    for position, (line_index, match) in enumerate(unique):
        end = unique[position + 1][0] if position + 1 < len(unique) else len(lines)
        fragments = [match.group(2)]
        for line in lines[line_index + 1 : end]:
            if line.strip() and len(line) - len(line.lstrip()) < 10:
                break
            if line.strip():
                fragments.append(line.strip())
        temporary: dict[str, RuleRecord] = {}
        _flush_rule(
            temporary,
            match.group(1),
            fragments,
            source_name,
            digest,
            page_number,
        )
        records.extend(temporary.values())
    return tuple(records)


def _general_summary_records(
    pages: list[str],
    *,
    source_name: str,
    digest: str,
) -> tuple[RuleRecord, ...]:
    expected = {f"GR-{number}" for number in range(1, 9)}
    for page_number, page in enumerate(pages, 1):
        matches = list(_GENERAL_RE.finditer(page))
        if {match.group(1) for match in matches} != expected:
            continue
        return tuple(
            RuleRecord(
                rule_id=match.group(1),
                requirement=match.group(2).strip(),
                treatment=_treatment(match.group(1)),
                review_state=ReviewState.DRAFT,
                source=_source_location(source_name, digest, page_number),
                notes="General recommendation heading; full text review is required.",
            )
            for match in matches
        )
    return ()


def extract_rule_candidates(text: str, *, source_name: str) -> tuple[RuleRecord, ...]:
    """Extract 53 numbered rules and eight general recommendations."""

    digest = sha256_digest(text.encode("utf-8"))
    pages = text.split("\f")
    records: dict[str, RuleRecord] = {}
    for page_number, page in enumerate(pages, 1):
        if "Summary of the rules" in page:
            for record in _numbered_summary_records(
                page,
                page_number=page_number,
                source_name=source_name,
                digest=digest,
            ):
                records.setdefault(record.rule_id, record)
    for record in _general_summary_records(pages, source_name=source_name, digest=digest):
        records[record.rule_id] = record
    return tuple(sorted(records.values(), key=_rule_sort_key))


def _rule_sort_key(rule: RuleRecord) -> tuple[int, int]:
    if rule.rule_id.startswith("GR-"):
        return (10, int(rule.rule_id.removeprefix("GR-")))
    section, number = rule.rule_id.split(".", maxsplit=1)
    return (int(section), int(number))


def _candidate_id(status: str, word: str, part_of_speech: str) -> str:
    value = f"{status}\0{word}\0{part_of_speech}".encode()
    return f"candidate_{hashlib.sha256(value).hexdigest()[:16]}"


def extract_dictionary_candidates(
    text: str,
    *,
    source_name: str,
) -> tuple[DictionaryCandidate, ...]:
    """Extract draft dictionary row keys without treating them as reviewed data."""

    digest = sha256_digest(text.encode("utf-8"))
    pages = text.split("\f")
    candidates: dict[tuple[str, str, str], DictionaryCandidate] = {}
    for page_number, page in enumerate(pages[148:434], 149):
        lines = page.splitlines()
        for index, line in enumerate(lines):
            if not line or line[0].isspace():
                continue
            match = _POS_RE.search(line)
            if match is None or match.start() > 15:
                continue
            displayed = line[: match.start()].strip().rstrip(",")
            if not displayed and index:
                displayed = lines[index - 1][:16].strip().rstrip(",")
            if not displayed or displayed == "part of speech":
                continue
            normalized = " ".join(displayed.casefold().split())
            part_of_speech = match.group().casefold()
            status: Literal["approved", "unapproved"] = (
                "approved" if displayed.isupper() else "unapproved"
            )
            key = (status, normalized, part_of_speech)
            candidates.setdefault(
                key,
                DictionaryCandidate(
                    candidate_id=_candidate_id(status, normalized, part_of_speech),
                    displayed_word=displayed,
                    normalized_word=normalized,
                    status=status,
                    part_of_speech=part_of_speech,
                    raw_line=line.rstrip(),
                    source=_source_location(source_name, digest, page_number),
                ),
            )
    return tuple(candidates.values())


def build_conformance_matrix(rules: Iterable[RuleRecord]) -> tuple[ConformanceRecord, ...]:
    """Build the explicit initial treatment and implementation matrix."""

    records: list[ConformanceRecord] = []
    for rule in rules:
        checkers = _CHECKERS_BY_RULE.get(rule.rule_id, ())
        scope: Literal["full", "partial", "none"]
        gate: Literal["blocking", "report_only", "human_review"]
        if rule.rule_id in _FULL_RULES:
            scope = "full"
            gate = "blocking"
            reason = "The complete mechanically testable requirement is implemented."
        elif checkers:
            scope = "partial"
            gate = "report_only"
            reason = "Only the conclusive mechanical subset is implemented."
        elif rule.treatment is RuleTreatment.LEARNED:
            scope = "none"
            gate = "report_only"
            reason = "The requirement needs contextual detection or rewriting evidence."
        else:
            scope = "none"
            gate = "human_review"
            reason = "The requirement is not suitable for conclusive automatic checking."
        records.append(
            ConformanceRecord(
                rule_id=rule.rule_id,
                deterministic_checkers=checkers,
                learned_role="detector" if rule.treatment is RuleTreatment.LEARNED else None,
                coverage_scope=scope,
                release_gate=gate,
                reason=reason,
            )
        )
    return tuple(records)


def extraction_audit(
    rules: Iterable[RuleRecord],
    candidates: Iterable[DictionaryCandidate],
) -> dict[str, object]:
    rule_items = tuple(rules)
    dictionary_items = tuple(candidates)
    actual = {
        "numbered_rules": sum(not rule.rule_id.startswith("GR-") for rule in rule_items),
        "general_rules": sum(rule.rule_id.startswith("GR-") for rule in rule_items),
        "approved_words": sum(item.status == "approved" for item in dictionary_items),
        "unapproved_words": sum(item.status == "unapproved" for item in dictionary_items),
    }
    return {
        "expected_counts": _EXPECTED,
        "candidate_counts": actual,
        "counts_match": actual == _EXPECTED,
        "review_state": "draft",
        "runtime_eligible": False,
        "notes": [
            "Candidate rows are not controlled-vocabulary authority.",
            "Meanings, forms, alternatives, examples, and malformed wrapped rows need review.",
        ],
    }


def write_draft_extraction(source: Path, output_dir: Path) -> dict[str, object]:
    """Write deterministic draft artifacts and an explicit reconciliation audit."""

    text = source.read_text(encoding="utf-8")
    rules = extract_rule_candidates(text, source_name=str(source))
    candidates = extract_dictionary_candidates(text, source_name=str(source))
    conformance = build_conformance_matrix(rules)
    audit = extraction_audit(rules, candidates)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "rules.json", [item.model_dump(mode="json") for item in rules])
    _write_json(
        output_dir / "dictionary-candidates.json",
        [item.model_dump(mode="json") for item in candidates],
    )
    _write_json(
        output_dir / "conformance.json",
        [item.model_dump(mode="json") for item in conformance],
    )
    _write_json(output_dir / "extraction-audit.json", audit)
    return audit


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
