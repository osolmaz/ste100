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
from ste100.models import DictionaryEntry, RuleRecord, SourceLocation, StandardManifest

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
    approved = re.match(r"^([A-Z][A-Z0-9 /'\-]*?)(?=\s+[A-Z][a-z])", line)
    if approved is not None:
        return approved.group(1).strip()
    unapproved = re.match(r"^([a-z][a-z0-9 /'\-]*?)(?=\s+[A-Z]{2,})", line)
    if unapproved is not None:
        return unapproved.group(1).strip()
    return re.sub(r"\s+(?:[A-Z][a-z]{0,12}|[A-Z]{1,8})$", "", first_column).strip()


def _is_approved_headword(word: str) -> bool:
    without_qualifiers = re.sub(r"\([^)]*\)", "", word)
    letters = "".join(character for character in without_qualifiers if character.isalpha())
    return bool(letters) and letters.isupper()


def _canonical_word(displayed: str) -> tuple[str, tuple[str, ...], str | None]:
    value = displayed.replace("…", "...").strip().strip(",")
    parenthetical = re.fullmatch(r"([^()]*)\(([^()]*)\)", value)
    aliases: list[str] = []
    qualifier: str | None = None
    if parenthetical is not None:
        outside = parenthetical.group(1).strip()
        inside = parenthetical.group(2).strip()
        if outside and inside.casefold().startswith("or "):
            value = outside
            aliases.append(inside[3:].strip())
        elif outside and inside:
            value = outside
            qualifier = (
                inside
                if any(token.startswith(outside.casefold()) for token in inside.casefold().split())
                else f"{outside} {inside}"
            )
        else:
            value = outside or inside
    value = re.sub(r"\s+", " ", value).strip().casefold()
    aliases = [re.sub(r"\s+", " ", item).strip().casefold() for item in aliases if item]
    if qualifier is not None:
        qualifier = re.sub(r"\s+", " ", qualifier).strip().casefold()
    return value, tuple(dict.fromkeys(aliases)), qualifier


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


def _merge_dictionary_entries(
    existing: DictionaryEntry, incoming: DictionaryEntry
) -> DictionaryEntry:
    if existing.qualifier is None and incoming.qualifier is None:
        raise ValueError(f"duplicate dictionary row without a qualifier: {existing.word!r}")
    if existing.qualifier is not None and incoming.qualifier is not None:
        raise ValueError(f"duplicate qualified dictionary row: {existing.word!r}")
    if existing.source.page != incoming.source.page:
        raise ValueError(f"duplicate dictionary rows cross pages: {existing.word!r}")
    qualified = existing if existing.qualifier is not None else incoming
    base = incoming if existing.qualifier is not None else existing
    source_rows = "+".join(
        value for value in (existing.source.row, incoming.source.row) if value is not None
    )
    return base.model_copy(
        update={
            "approved_forms": tuple(
                dict.fromkeys(
                    (*base.approved_forms, qualified.qualifier, *qualified.approved_forms)
                )
            ),
            "alternatives": tuple(dict.fromkeys((*base.alternatives, *qualified.alternatives))),
            "source": base.source.model_copy(update={"row": source_rows}),
        }
    )


def build_dictionary(text: str) -> tuple[DictionaryEntry, ...]:
    """Build source-traceable runtime dictionary rows."""

    digest = sha256_digest(text.encode("utf-8"))
    entries: list[DictionaryEntry] = []
    positions: dict[tuple[str, str, str], int] = {}
    for row_number, row in enumerate(_dictionary_rows(text), 1):
        word, aliases, qualifier = _canonical_word(row.word)
        entry = DictionaryEntry(
            entry_id=_entry_id(row.status, word, row.part_of_speech, row_number),
            word=word,
            qualifier=qualifier,
            status=row.status,
            parts_of_speech=(row.part_of_speech,),
            approved_forms=_forms(row, aliases),
            alternatives=_alternatives(row),
            source=_source(digest, row.page, row=f"dictionary-row-{row_number}"),
        )
        key = (entry.status, entry.word, row.part_of_speech)
        position = positions.get(key)
        if position is None:
            positions[key] = len(entries)
            entries.append(entry)
        else:
            entries[position] = _merge_dictionary_entries(entries[position], entry)
    return tuple(entries)


def build_rules(text: str) -> tuple[RuleRecord, ...]:
    """Extract rule and general-recommendation summaries from Issue 9."""

    return extract_rule_candidates(text, source_name=_SOURCE_FILE)


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
    output.mkdir(parents=True, exist_ok=True)
    for stale_name in ("conformance.json", "examples.json"):
        (output / stale_name).unlink(missing_ok=True)
    (output / "__init__.py").write_text(
        '"""Bundled ASD-STE100 Issue 9 structured data."""\n', encoding="utf-8"
    )
    artifacts: dict[str, tuple[BaseModel, ...]] = {
        "rules.json": rules,
        "dictionary.json": dictionary,
    }
    for name, records in artifacts.items():
        _write_models(output / name, records)
    manifest = StandardManifest(
        format_version="1",
        standard_id="ASD-STE100",
        issue=9,
        source=_source(digest, 1),
        file_digests={name: _file_digest(output / name) for name in artifacts},
    )
    (output / "standard.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    return manifest
