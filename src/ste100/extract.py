"""Extract Issue 9 rule requirements from the exact text export."""

from __future__ import annotations

import hashlib
import re

from ste100.models import RuleRecord, SourceLocation

_RULE_RE = re.compile(r"^\s*Rule\s+(\d+\.\d+)\s+(.*\S)\s*$")
_GENERAL_RE = re.compile(
    r"^[ \t]*(GR-[1-8])[ \t]+(.+?)(?:[ \t]{2,}|$)",
    re.MULTILINE,
)


def sha256_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _source_location(source_name: str, digest: str, page: int) -> SourceLocation:
    return SourceLocation(source_file=source_name, page=page, source_digest=digest)


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
        records.append(
            RuleRecord(
                rule_id=match.group(1),
                requirement=" ".join(fragment.strip() for fragment in fragments),
                source=_source_location(source_name, digest, page_number),
            )
        )
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
                source=_source_location(source_name, digest, page_number),
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
        if "Summary of the rules" not in page:
            continue
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
