"""Protect facts and caller-controlled text before learned rewriting."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from ste100.document import char_to_byte_offsets, slice_bytes
from ste100.models import ByteRange, ProjectDictionary, ProtectedSpan
from ste100.terminology import TermMatcher

_CODE_RE = re.compile(r"```[\s\S]*?```|`[^`\n]+`")
_URL_RE = re.compile(r"https?://[^\s<>]+")
_NUMBER_RE = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?(?:\s*(?:°[CF]|%|[A-Za-z]{1,8}))?(?!\w)")
ProtectedKind = Literal[
    "project_term",
    "number",
    "unit",
    "identifier",
    "url",
    "code",
    "caller",
]

_IDENTIFIER_RE = re.compile(
    r"\b(?:[A-Z]{2,}[A-Z0-9_-]*|[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+|"
    r"[a-z]+[A-Z][A-Za-z0-9]*)\b"
)


class ProtectedContentError(ValueError):
    """Raised when a rewrite changes, drops, duplicates, or reorders protected content."""


@dataclass(frozen=True, slots=True)
class ProtectedDocument:
    source_text: str
    masked_text: str
    spans: tuple[ProtectedSpan, ...]
    sentinel_prefix: str
    sentinels: tuple[str, ...]
    originals: tuple[str, ...]

    def restore(self, candidate: str) -> str:
        """Validate all sentinels and restore the exact protected source strings."""

        pattern = re.compile(re.escape(self.sentinel_prefix) + r"\d{4}__")
        found = tuple(match.group() for match in pattern.finditer(candidate))
        if found != self.sentinels:
            raise ProtectedContentError(
                "protected sentinels were changed, dropped, duplicated, or reordered"
            )
        restored = candidate
        for sentinel, original in zip(self.sentinels, self.originals, strict=True):
            if restored.count(sentinel) != 1:
                raise ProtectedContentError(f"expected exactly one occurrence of {sentinel}")
            restored = restored.replace(sentinel, original)
        if pattern.search(restored):
            raise ProtectedContentError("candidate contains an unknown protected sentinel")
        return restored


@dataclass(frozen=True, slots=True)
class _Candidate:
    start: int
    end: int
    kind: ProtectedKind
    priority: int


def _digest(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _span_id(kind: ProtectedKind, byte_range: ByteRange, text: str) -> str:
    raw = f"{kind}\0{byte_range.start}\0{byte_range.end}\0{text}".encode()
    return f"span_{hashlib.sha256(raw).hexdigest()[:16]}"


def _sentinel_prefix(text: str) -> str:
    for nonce in range(1000):
        digest = hashlib.sha256(f"{nonce}\0{text}".encode()).hexdigest()[:12]
        prefix = f"__STE100_{digest}_"
        if prefix not in text:
            return prefix
    raise ProtectedContentError("could not create a collision-free sentinel namespace")


def _byte_to_char(text: str, offset: int) -> int:
    encoded = text.encode("utf-8")
    if offset < 0 or offset > len(encoded):
        raise ProtectedContentError("caller range is outside the source text")
    try:
        return len(encoded[:offset].decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ProtectedContentError("caller range does not align with UTF-8") from error


def _regex_candidates(
    text: str,
    pattern: re.Pattern[str],
    kind: ProtectedKind,
    priority: int,
) -> list[_Candidate]:
    return [
        _Candidate(start=match.start(), end=match.end(), kind=kind, priority=priority)
        for match in pattern.finditer(text)
    ]


def _select_non_overlapping(candidates: list[_Candidate]) -> tuple[_Candidate, ...]:
    selected: list[_Candidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (item.priority, item.start, -(item.end - item.start)),
    ):
        if any(candidate.start < item.end and item.start < candidate.end for item in selected):
            continue
        selected.append(candidate)
    return tuple(sorted(selected, key=lambda item: item.start))


def protect_text(
    text: str,
    *,
    project_dictionary: ProjectDictionary | None = None,
    caller_ranges: tuple[ByteRange, ...] = (),
) -> ProtectedDocument:
    """Replace facts and approved terms with ordered, auditable sentinels."""

    candidates: list[_Candidate] = []
    for byte_range in caller_ranges:
        try:
            slice_bytes(text, byte_range)
        except ValueError as error:
            raise ProtectedContentError(str(error)) from error
        candidates.append(
            _Candidate(
                start=_byte_to_char(text, byte_range.start),
                end=_byte_to_char(text, byte_range.end),
                kind="caller",
                priority=0,
            )
        )
    candidates.extend(_regex_candidates(text, _CODE_RE, "code", 1))
    candidates.extend(_regex_candidates(text, _URL_RE, "url", 2))
    if project_dictionary is not None:
        offsets = char_to_byte_offsets(text)
        byte_to_char = {byte: char for char, byte in enumerate(offsets)}
        for term_match in TermMatcher(project_dictionary).find(text):
            candidates.append(
                _Candidate(
                    start=byte_to_char[term_match.byte_range.start],
                    end=byte_to_char[term_match.byte_range.end],
                    kind="project_term",
                    priority=3,
                )
            )
    candidates.extend(_regex_candidates(text, _IDENTIFIER_RE, "identifier", 4))
    for number_match in _NUMBER_RE.finditer(text):
        kind: ProtectedKind = (
            "unit"
            if any(character.isalpha() or character in "°%" for character in number_match.group())
            else "number"
        )
        candidates.append(
            _Candidate(
                start=number_match.start(),
                end=number_match.end(),
                kind=kind,
                priority=5,
            )
        )

    selected = _select_non_overlapping(candidates)
    offsets = char_to_byte_offsets(text)
    sentinel_prefix = _sentinel_prefix(text)
    masked_parts: list[str] = []
    spans: list[ProtectedSpan] = []
    sentinels: list[str] = []
    originals: list[str] = []
    cursor = 0
    for index, candidate in enumerate(selected):
        sentinel = f"{sentinel_prefix}{index:04d}__"
        original = text[candidate.start : candidate.end]
        byte_range = ByteRange(start=offsets[candidate.start], end=offsets[candidate.end])
        masked_parts.extend((text[cursor : candidate.start], sentinel))
        spans.append(
            ProtectedSpan(
                span_id=_span_id(candidate.kind, byte_range, original),
                kind=candidate.kind,
                byte_range=byte_range,
                text_digest=_digest(original),
            )
        )
        sentinels.append(sentinel)
        originals.append(original)
        cursor = candidate.end
    masked_parts.append(text[cursor:])
    return ProtectedDocument(
        source_text=text,
        masked_text="".join(masked_parts),
        spans=tuple(spans),
        sentinel_prefix=sentinel_prefix,
        sentinels=tuple(sentinels),
        originals=tuple(originals),
    )
