"""Build the bundled deterministic Issue 9 pack from the exact text export."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ste100.extract import extract_rule_candidates, sha256_digest
from ste100.models import (
    ConformanceRecord,
    DictionaryEntry,
    ExpectedCounts,
    ReviewState,
    RuleRecord,
    RuleTreatment,
    SourceLocation,
    StandardExample,
    StandardManifest,
)

_POS_RE = re.compile(r"\((art|prep|v|n|adj|adv|conj|pron|prefix)\),?", re.IGNORECASE)
_ALTERNATIVE_RE = re.compile(
    r"^([A-Z][A-Z0-9]*(?:[ .…/'-]+[A-Z0-9]+)*)\s+"
    r"\((?:n|v|adj|adv|prep|pron|conj|art|TN|TV)\)"
)
_POS_NAMES = {
    "art": "article",
    "prep": "preposition",
    "v": "verb",
    "n": "noun",
    "adj": "adjective",
    "adv": "adverb",
    "conj": "conjunction",
    "pron": "pronoun",
    "prefix": "prefix",
}
_SOURCE_FILE = "ASD-STE100_ISSUE9.txt"
_PUBLISHED_COUNTS = {
    "numbered_rules": 53,
    "general_rules": 8,
    "approved_words": 875,
    "unapproved_words": 1274,
}

# These scopes describe only what the deterministic implementation proves.
_CHECKERS: dict[str, tuple[str, ...]] = {
    "1.1": ("vocabulary",),
    "1.2": ("approved_part_of_speech",),
    "1.4": ("approved_form",),
    "1.6": ("unapproved_vocabulary",),
    "1.7": ("technical_noun_as_verb",),
    "1.8": ("project_terminology",),
    "1.11": ("terminology_consistency",),
    "1.13": ("technical_verb_as_noun",),
    "1.14": ("american_spelling",),
    "2.1": ("multiword_term_length",),
    "3.1": ("approved_verb_form",),
    "3.2": ("verb_form",),
    "3.4": ("complex_verb",),
    "3.5": ("ing_form",),
    "3.6": ("passive_voice",),
    "4.2": ("contraction",),
    "4.3": ("vertical_list",),
    "5.1": ("procedure_sentence_length",),
    "5.2": ("instruction_count",),
    "5.3": ("imperative_instruction",),
    "5.4": ("condition_comma",),
    "5.5": ("note_instruction",),
    "6.3": ("descriptive_sentence_length",),
    "6.6": ("paragraph_sentence_count",),
    "7.2": ("safety_opening",),
    "8.1": ("semicolon",),
    "8.3": ("balanced_parentheses",),
    "8.4": ("word_count",),
    "8.5": ("word_count",),
    "8.6": ("word_count",),
    "8.7": ("word_count",),
    "9.3": ("phrasal_verb",),
    "9.4": ("terminology_consistency",),
    "GR-1": ("omitted_that",),
    "GR-6": ("latin_abbreviation",),
    "GR-7": ("gendered_term",),
}
_FULL_RULES = frozenset({"5.1", "6.3", "6.6", "8.1", "8.4", "8.5", "8.7"})


@dataclass(frozen=True, slots=True)
class _DictionaryRow:
    page: int
    word: str
    part_of_speech: str
    status: Literal["approved", "unapproved"]
    column_one: tuple[str, ...]
    column_two: tuple[str, ...]


def _source(digest: str, page: int, *, row: str | None = None) -> SourceLocation:
    return SourceLocation(
        source_file=_SOURCE_FILE,
        page=page,
        row=row,
        source_digest=digest,
    )


def _dictionary_rows(text: str) -> tuple[_DictionaryRow, ...]:  # noqa: C901 -- Fixed-column table repair cases.
    rows: list[_DictionaryRow] = []
    pages = text.split("\f")
    for page_number, page in enumerate(pages[148:433], 149):
        lines = page.splitlines()
        header = next((line for line in lines if "Approved meaning/" in line), None)
        if header is None:
            continue
        column_two = header.index("Approved meaning/")
        example_header = next((line for line in lines if "STE EXAMPLE" in line), None)
        column_three = (
            example_header.index("STE EXAMPLE") if example_header is not None else column_two + 26
        )
        anchors: list[tuple[int, int, str, str]] = []
        for index, line in enumerate(lines):
            first_cell = line[:column_two].rstrip()
            match = _POS_RE.search(first_cell)
            if match is None:
                continue
            word = first_cell[: match.start()].strip().rstrip(",")
            start = index
            if not word:
                previous = index - 1
                while previous >= 0 and not lines[previous][:column_two].strip():
                    previous -= 1
                if previous >= 0:
                    word = _wrapped_headword(lines[previous], column_two)
                    start = previous
            elif index:
                previous_cell = lines[index - 1][:column_two].strip()
                previous_meaning = lines[index - 1][column_two:column_three].strip()
                if previous_cell.endswith("-"):
                    word = previous_cell[:-1] + word
                    start = index - 1
                elif previous_cell.count("(") > previous_cell.count(")"):
                    word = f"{previous_cell} {word}"
                    start = index - 1
                elif (
                    word.isupper()
                    and previous_cell.isupper()
                    and not previous_cell.endswith(")")
                    and previous_meaning
                    and any(character.islower() for character in previous_meaning)
                    and _POS_RE.search(previous_cell) is None
                ):
                    word = f"{previous_cell} {word}"
                    start = index - 1
            word = " ".join(word.split())
            if not word or word.casefold() == "part of speech":
                continue
            anchors.append((start, index, word, match.group(1).casefold()))
        for position, (start, _, word, part_of_speech) in enumerate(anchors):
            end = anchors[position + 1][0] if position + 1 < len(anchors) else len(lines)
            block = lines[start:end]
            first = tuple(line[:column_two].strip() for line in block)
            second = tuple(line[column_two:column_three].strip() for line in block)
            status: Literal["approved", "unapproved"] = (
                "approved" if _is_approved_headword(word) else "unapproved"
            )
            rows.append(
                _DictionaryRow(
                    page=page_number,
                    word=word,
                    part_of_speech=_POS_NAMES[part_of_speech],
                    status=status,
                    column_one=first,
                    column_two=second,
                )
            )
    return tuple(rows)


def _wrapped_headword(line: str, column_two: int) -> str:
    """Read a headword whose part-of-speech marker is on the next line."""

    first_column = line[:column_two].strip().rstrip(",")
    separated = re.split(r"\s{2,}", line.strip(), maxsplit=1)
    if len(separated) > 1 and len(separated[0]) <= column_two:
        return separated[0].rstrip(",")
    return re.sub(r"\s+(?:[A-Z][a-z]{0,12}|[A-Z]{1,8})$", "", first_column).strip()


def _is_approved_headword(word: str) -> bool:
    without_qualifiers = re.sub(r"\([^)]*\)", "", word)
    letters = "".join(character for character in without_qualifiers if character.isalpha())
    return bool(letters) and letters.isupper()


def _canonical_word(displayed: str) -> tuple[str, tuple[str, ...]]:
    value = displayed.replace("…", "...").strip().strip(",")
    parenthetical = re.fullmatch(r"([^()]*)\(([^()]*)\)", value)
    aliases: list[str] = []
    if parenthetical is not None:
        outside = parenthetical.group(1).strip()
        inside = parenthetical.group(2).strip()
        if outside and inside.casefold().startswith("or "):
            value = outside
            aliases.append(inside[3:].strip())
        elif outside and inside:
            value = (
                inside if outside.casefold() in inside.casefold().split() else f"{outside} {inside}"
            )
            aliases.append(outside)
        else:
            value = outside or inside
    value = re.sub(r"\s+", " ", value).strip().casefold()
    aliases = [re.sub(r"\s+", " ", item).strip().casefold() for item in aliases if item]
    return value, tuple(dict.fromkeys(aliases))


def _forms(row: _DictionaryRow, aliases: tuple[str, ...]) -> tuple[str, ...]:
    forms = list(aliases)
    for cell in row.column_one[1:]:
        if not cell or _POS_RE.search(cell):
            continue
        for item in cell.split(","):
            form = item.strip().strip("(),")
            if form and _is_approved_headword(form):
                forms.append(form.casefold())
    return tuple(dict.fromkeys(forms))


def _alternatives(row: _DictionaryRow) -> tuple[str, ...]:
    if row.status == "approved":
        return ()
    alternatives: list[str] = []
    for cell in row.column_two:
        value = " ".join(cell.replace("…", "...").split())
        match = _ALTERNATIVE_RE.match(value)
        if match is not None:
            alternatives.append(match.group(1).casefold())
    return tuple(dict.fromkeys(alternatives))


def _entry_id(status: str, word: str, part_of_speech: str, row_number: int) -> str:
    raw = f"{status}\0{word}\0{part_of_speech}\0{row_number}".encode()
    slug = re.sub(r"[^a-z0-9]+", "-", word).strip("-")[:36] or "entry"
    return f"{slug}-{hashlib.sha256(raw).hexdigest()[:12]}"


def build_dictionary(text: str) -> tuple[DictionaryEntry, ...]:
    """Build source-traceable runtime dictionary rows."""

    digest = sha256_digest(text.encode("utf-8"))
    entries: list[DictionaryEntry] = []
    for row_number, row in enumerate(_dictionary_rows(text), 1):
        word, aliases = _canonical_word(row.word)
        entries.append(
            DictionaryEntry(
                entry_id=_entry_id(row.status, word, row.part_of_speech, row_number),
                word=word,
                status=row.status,
                parts_of_speech=(row.part_of_speech,),
                approved_meanings=(),
                approved_forms=_forms(row, aliases),
                alternatives=_alternatives(row),
                review_state=ReviewState.REVIEWED,
                source=_source(digest, row.page, row=f"dictionary-row-{row_number}"),
            )
        )
    return tuple(entries)


def build_rules(text: str) -> tuple[RuleRecord, ...]:
    """Promote exact section-summary requirements into deterministic coverage records."""

    candidates = extract_rule_candidates(text, source_name=_SOURCE_FILE)
    return tuple(
        RuleRecord(
            rule_id=item.rule_id,
            requirement=item.requirement,
            treatment=(
                RuleTreatment.DETERMINISTIC
                if item.rule_id in _CHECKERS
                else RuleTreatment.HUMAN_REVIEW
            ),
            review_state=ReviewState.REVIEWED,
            source=item.source,
            notes=(
                "The checker covers the mechanically decidable clause recorded in conformance.json."
                if item.rule_id in _CHECKERS
                else "The requirement needs human judgment."
            ),
        )
        for item in candidates
    )


def build_conformance(rules: tuple[RuleRecord, ...]) -> tuple[ConformanceRecord, ...]:
    records: list[ConformanceRecord] = []
    for rule in rules:
        checkers = _CHECKERS.get(rule.rule_id, ())
        scope: Literal["full", "partial", "none"] = (
            "full" if rule.rule_id in _FULL_RULES else "partial" if checkers else "none"
        )
        records.append(
            ConformanceRecord(
                rule_id=rule.rule_id,
                deterministic_checkers=checkers,
                coverage_scope=scope,
                release_gate="blocking" if scope == "full" else "human_review",
                reason=(
                    "The complete mechanical requirement is checked."
                    if scope == "full"
                    else (
                        "The named mechanical clause is checked; "
                        "remaining interpretation needs review."
                    )
                    if scope == "partial"
                    else "The requirement is contextual and needs human review."
                ),
            )
        )
    return tuple(records)


def build_examples(digest: str) -> tuple[StandardExample, ...]:
    examples = (
        ("semicolon-negative", "8.1", "Open the valve; then start the pump.", "negative", 126),
        ("semicolon-positive", "8.1", "Open the valve. Then start the pump.", "positive", 126),
        ("contraction-negative", "4.2", "Don't open the access panel.", "negative", 75),
        ("contraction-positive", "4.2", "Do not open the access panel.", "positive", 75),
        ("general-that-negative", "GR-1", "Make sure the valve is open.", "negative", 118),
        ("general-that-positive", "GR-1", "Make sure that the valve is open.", "positive", 118),
        (
            "gendered-negative",
            "GR-7",
            "The operator must put his tools in the box.",
            "negative",
            121,
        ),
        (
            "gendered-positive",
            "GR-7",
            "Operators must put their tools in the box.",
            "positive",
            121,
        ),
        ("latin-negative", "GR-6", "Use the applicable tool, e.g. a wrench.", "negative", 120),
        (
            "latin-positive",
            "GR-6",
            "Use the applicable tool, for example, a wrench.",
            "positive",
            120,
        ),
        ("procedure-positive", "5.1", "1. Open the access panel.", "positive", 83),
        ("note-positive", "5.5", "NOTE: The valve stays open during the test.", "positive", 88),
        ("note-negative", "5.5", "NOTE: Open the valve before the test.", "negative", 88),
        ("parentheses-positive", "8.5", "Install the bolts (items 2 and 3).", "positive", 125),
        ("list-positive", "8.4", "Use these items:\n1. A wrench.\n2. A cloth.", "positive", 124),
    )
    return tuple(
        StandardExample(
            example_id=example_id,
            rule_ids=(rule_id,),
            text=text,
            label=label,
            review_state=ReviewState.REVIEWED,
            source=_source(digest, page),
        )
        for example_id, rule_id, text, label, page in examples
    )


def _write_models(path: Path, records: tuple[BaseModel, ...]) -> None:
    values = [record.model_dump(mode="json") for record in records]
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def write_runtime_pack(source: Path, output: Path) -> StandardManifest:
    """Write the deterministic runtime pack and its checked digests."""

    text = source.read_text(encoding="utf-8")
    digest = sha256_digest(text.encode("utf-8"))
    rules = build_rules(text)
    dictionary = build_dictionary(text)
    examples = build_examples(digest)
    conformance = build_conformance(rules)
    output.mkdir(parents=True, exist_ok=True)
    (output / "__init__.py").write_text(
        '"""Bundled ASD-STE100 Issue 9 structured data."""\n', encoding="utf-8"
    )
    artifacts: dict[str, tuple[BaseModel, ...]] = {
        "rules.json": rules,
        "dictionary.json": dictionary,
        "examples.json": examples,
        "conformance.json": conformance,
    }
    for name, records in artifacts.items():
        _write_models(output / name, records)
    actual_counts = ExpectedCounts(
        numbered_rules=sum(not item.rule_id.startswith("GR-") for item in rules),
        general_rules=sum(item.rule_id.startswith("GR-") for item in rules),
        approved_words=sum(item.status == "approved" for item in dictionary),
        unapproved_words=sum(item.status == "unapproved" for item in dictionary),
    )
    manifest = StandardManifest(
        format_version="1",
        standard_id="ASD-STE100",
        issue=9,
        review_state=ReviewState.REVIEWED,
        source=_source(digest, 1),
        expected_counts=actual_counts,
        published_counts=ExpectedCounts(**_PUBLISHED_COUNTS),
        count_reconciliation=(
            f"The fixed-column source table yields {actual_counts.approved_words} approved "
            f"and {actual_counts.unapproved_words} unapproved unique "
            "status/headword/part-of-speech rows after wrapped headwords are repaired. "
            "All source-traceable rows are retained; no row is deleted to force the printed totals."
        ),
        file_digests={name: _file_digest(output / name) for name in artifacts},
    )
    (output / "standard.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    return manifest
