"""Lossless document parsing with half-open UTF-8 byte offsets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ste100.models import ByteRange

_SENTENCE_END = frozenset(".!?")
_ABBREVIATIONS = frozenset({"e.g.", "i.e.", "etc.", "mr.", "mrs.", "ms.", "dr.", "fig."})
_WORD_RE = re.compile(
    r"https?://\S+"
    r'|"[^"\n]+"'
    r"|\([^()\n]*\)"
    r"|\b\d+(?:[.,]\d+)?(?:\s*[A-Za-z°%]+)?\b"
    r"|\b[A-Za-z0-9]+(?:[-_/][A-Za-z0-9]+)+\b"
    r"|\b[A-Za-z][A-Za-z0-9]*(?:'[A-Za-z]+)?\b",
)
_PROCEDURE_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]|[a-z][.)])\s+", re.IGNORECASE)
_PAREN_RE = re.compile(r"\(([^()\n]+)\)")
_SAFETY_LABEL_RE = re.compile(r"^\s*(?:WARNING|CAUTION):\s*", re.IGNORECASE)
_LIST_RE = re.compile(r"^\s*(?:[-*•]|[A-Z][.)])\s+")


class BlockKind(StrEnum):
    PARAGRAPH = "paragraph"
    PROCEDURE = "procedure"
    LIST = "list"
    NOTE = "note"
    CAUTION = "caution"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    byte_range: ByteRange


@dataclass(frozen=True, slots=True)
class Sentence:
    text: str
    byte_range: ByteRange
    tokens: tuple[Token, ...]

    @property
    def word_count(self) -> int:
        return len(self.tokens)


@dataclass(frozen=True, slots=True)
class Block:
    kind: BlockKind
    text: str
    byte_range: ByteRange
    sentences: tuple[Sentence, ...]


@dataclass(frozen=True, slots=True)
class Document:
    text: str
    blocks: tuple[Block, ...]

    @property
    def sentences(self) -> tuple[Sentence, ...]:
        return tuple(sentence for block in self.blocks for sentence in block.sentences)


def char_to_byte_offsets(text: str) -> tuple[int, ...]:
    """Return the UTF-8 byte offset for each character boundary."""

    offsets = [0]
    total = 0
    for character in text:
        total += len(character.encode("utf-8"))
        offsets.append(total)
    return tuple(offsets)


def slice_bytes(text: str, byte_range: ByteRange) -> str:
    """Slice text at validated UTF-8 byte boundaries."""

    encoded = text.encode("utf-8")
    try:
        return encoded[byte_range.start : byte_range.end].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("range does not align with UTF-8 character boundaries") from error


def tokenize(text: str, *, char_start: int = 0, full_text: str | None = None) -> tuple[Token, ...]:
    """Tokenize text using the STE word-count exceptions that can be deterministic."""

    source = full_text if full_text is not None else text
    offsets = char_to_byte_offsets(source)
    tokens: list[Token] = []
    for match in _WORD_RE.finditer(text):
        start = char_start + match.start()
        end = char_start + match.end()
        tokens.append(
            Token(
                text=match.group(),
                byte_range=ByteRange(start=offsets[start], end=offsets[end]),
            )
        )
    return tuple(tokens)


def _is_abbreviation(text: str, period_index: int) -> bool:
    if (
        period_index >= 1
        and period_index + 2 < len(text)
        and text[period_index - 1].isalpha()
        and text[period_index + 1].isalpha()
        and text[period_index + 2] == "."
    ):
        return True
    start = period_index
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    candidate = text[start : period_index + 1].lower()
    if candidate in _ABBREVIATIONS:
        return True
    return bool(re.fullmatch(r"(?:[A-Za-z]\.){2,}", candidate))


def _trimmed_range(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def _sentence_terminates(
    text: str,
    index: int,
    character: str,
    *,
    nested: bool,
    terminators: frozenset[str],
) -> bool:
    if character not in terminators or nested:
        return False
    numbered_marker = character == "." and text[:index].strip().isdigit() and index < 6
    return character != "." or not (_is_abbreviation(text, index) or numbered_marker)


def _outer_sentence_ranges(
    text: str,
    *,
    colon_terminates: bool = False,
) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    start = 0
    depth = 0
    quote_open = False
    terminators = frozenset(_SENTENCE_END | ({":"} if colon_terminates else set()))
    for index, character in enumerate(text):
        if character == '"':
            quote_open = not quote_open
        if character == "(":
            depth += 1
        if character == ")" and depth:
            depth -= 1
        if not _sentence_terminates(
            text,
            index,
            character,
            nested=bool(depth or quote_open),
            terminators=terminators,
        ):
            continue
        end = index + 1
        trimmed = _trimmed_range(text, start, end)
        if trimmed is not None:
            ranges.append(trimmed)
        start = end
    trailing = _trimmed_range(text, start, len(text))
    if trailing is not None:
        ranges.append(trailing)
    return tuple(ranges)


def _parenthetical_sentence_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for match in _PAREN_RE.finditer(text):
        inner = match.group(1)
        if len(_WORD_RE.findall(inner)) < 2:
            continue
        for start, end in _outer_sentence_ranges(inner):
            ranges.append((match.start(1) + start, match.start(1) + end))
    return tuple(ranges)


def sentence_ranges(text: str, *, colon_terminates: bool = False) -> tuple[tuple[int, int], ...]:
    """Return outer and parenthetical sentence ranges without changing source text."""

    ranges = (
        *_outer_sentence_ranges(text, colon_terminates=colon_terminates),
        *_parenthetical_sentence_ranges(text),
    )
    return tuple(sorted(ranges, key=lambda item: (item[0], -item[1])))


def _classify_block(text: str) -> BlockKind:
    first = text.lstrip()
    upper = first.upper()
    if upper.startswith("WARNING:"):
        return BlockKind.WARNING
    if upper.startswith("CAUTION:"):
        return BlockKind.CAUTION
    if upper.startswith("NOTE:"):
        return BlockKind.NOTE
    if _PROCEDURE_RE.match(first):
        return BlockKind.PROCEDURE
    if _LIST_RE.match(first):
        return BlockKind.LIST
    return BlockKind.PARAGRAPH


def _block_char_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    position = 0
    for line in text.splitlines(keepends=True):
        line_end = position + len(line)
        if line.strip():
            if start is None:
                start = position
        elif start is not None:
            end = position
            while end > start and text[end - 1] in "\r\n":
                end -= 1
            ranges.append((start, end))
            start = None
        position = line_end
    if start is not None:
        end = len(text)
        while end > start and text[end - 1] in "\r\n":
            end -= 1
        ranges.append((start, end))
    return tuple(ranges)


def _tokens_for_sentence(
    sentence_text: str,
    *,
    absolute_start: int,
    full_text: str,
    block_kind: BlockKind,
) -> tuple[Token, ...]:
    content_start = 0
    if block_kind is BlockKind.PROCEDURE:
        marker = _PROCEDURE_RE.match(sentence_text)
        if marker is not None:
            content_start = marker.end()
    if block_kind in {BlockKind.WARNING, BlockKind.CAUTION}:
        label = _SAFETY_LABEL_RE.match(sentence_text)
        if label is not None:
            content_start = label.end()
    return tokenize(
        sentence_text[content_start:],
        char_start=absolute_start + content_start,
        full_text=full_text,
    )


def parse_document(text: str) -> Document:
    """Parse text into blocks and sentences while preserving all source offsets."""

    offsets = char_to_byte_offsets(text)
    blocks: list[Block] = []
    for char_start, char_end in _block_char_ranges(text):
        block_text = text[char_start:char_end]
        kind = _classify_block(block_text)
        sentence_items: list[Sentence] = []
        colon_terminates = kind is BlockKind.LIST
        for relative_start, relative_end in sentence_ranges(
            block_text,
            colon_terminates=colon_terminates,
        ):
            absolute_start = char_start + relative_start
            absolute_end = char_start + relative_end
            sentence_text = text[absolute_start:absolute_end]
            sentence_items.append(
                Sentence(
                    text=sentence_text,
                    byte_range=ByteRange(
                        start=offsets[absolute_start],
                        end=offsets[absolute_end],
                    ),
                    tokens=_tokens_for_sentence(
                        sentence_text,
                        absolute_start=absolute_start,
                        full_text=text,
                        block_kind=kind,
                    ),
                )
            )
        blocks.append(
            Block(
                kind=kind,
                text=block_text,
                byte_range=ByteRange(start=offsets[char_start], end=offsets[char_end]),
                sentences=tuple(sentence_items),
            )
        )
    return Document(text=text, blocks=tuple(blocks))
