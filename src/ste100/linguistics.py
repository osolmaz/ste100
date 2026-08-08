"""Optional pinned spaCy analysis for deterministic linguistic checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from ste100.document import char_to_byte_offsets
from ste100.models import ByteRange


@dataclass(frozen=True, slots=True)
class LinguisticToken:
    text: str
    lemma: str
    pos: str
    tag: str
    dependency: str
    token_index: int
    head_index: int
    morphology: frozenset[str]
    byte_range: ByteRange


@dataclass(frozen=True, slots=True)
class LinguisticSentence:
    text: str
    tokens: tuple[LinguisticToken, ...]
    byte_range: ByteRange


class LinguisticAnalyzer(Protocol):
    """Provide pinned linguistic evidence without deciding STE conformance."""

    @property
    def analyzer_id(self) -> str: ...

    def analyze(self, text: str) -> tuple[LinguisticSentence, ...]: ...


class SpacyAnalyzer:
    """Adapt the pinned spaCy English pipeline to stable checker records."""

    _MODEL_NAME = "en_core_web_sm"
    _MODEL_VERSION = "3.8.0"

    def __init__(self) -> None:
        try:
            import spacy
        except ImportError as error:  # pragma: no cover - depends on optional installation
            raise RuntimeError("install the 'spacy' extra to use linguistic checks") from error
        try:
            self._pipeline = spacy.load(self._MODEL_NAME)
        except OSError as error:  # pragma: no cover - depends on optional installation
            raise RuntimeError(f"spaCy pipeline is not installed: {self._MODEL_NAME}") from error
        components = set(self._pipeline.pipe_names)
        if "parser" not in components or not {"tagger", "morphologizer"} & components:
            raise RuntimeError("spaCy pipeline must provide a parser and a POS-producing component")
        version = self._pipeline.meta.get("version", "unknown")
        if version != self._MODEL_VERSION:
            raise RuntimeError(
                f"spaCy pipeline version must be {self._MODEL_VERSION}, got {version}"
            )
        self._analyzer_id = f"spacy:{self._MODEL_NAME}:{version}"

    @property
    def analyzer_id(self) -> str:
        return self._analyzer_id

    def analyze(self, text: str) -> tuple[LinguisticSentence, ...]:
        document = self._pipeline(text)
        offsets = char_to_byte_offsets(text)
        sentences: list[LinguisticSentence] = []
        for sentence in document.sents:
            tokens = tuple(
                LinguisticToken(
                    text=token.text,
                    lemma=token.lemma_.casefold(),
                    pos=token.pos_,
                    tag=token.tag_,
                    dependency=token.dep_,
                    token_index=token.i,
                    head_index=token.head.i,
                    morphology=frozenset(str(token.morph).split("|")),
                    byte_range=ByteRange(
                        start=offsets[token.idx],
                        end=offsets[token.idx + len(token.text)],
                    ),
                )
                for token in sentence
                if not token.is_space
            )
            sentences.append(
                LinguisticSentence(
                    text=sentence.text,
                    tokens=tokens,
                    byte_range=ByteRange(
                        start=offsets[sentence.start_char],
                        end=offsets[sentence.end_char],
                    ),
                )
            )
        return _merge_markers(text, tuple(sentences))


def _merge_markers(
    text: str, sentences: tuple[LinguisticSentence, ...]
) -> tuple[LinguisticSentence, ...]:
    merged: list[LinguisticSentence] = []
    for sentence in sentences:
        if merged and re.fullmatch(
            r"\s*(?:(?:\d+(?:\.\d+)*|[a-z])[.)]|NOTE:|WARNING:|CAUTION:)\s*",
            merged[-1].text,
            re.IGNORECASE,
        ):
            marker = merged.pop()
            byte_range = ByteRange(start=marker.byte_range.start, end=sentence.byte_range.end)
            merged.append(
                LinguisticSentence(
                    text=text.encode("utf-8")[byte_range.start : byte_range.end].decode("utf-8"),
                    tokens=(*marker.tokens, *sentence.tokens),
                    byte_range=byte_range,
                )
            )
        else:
            merged.append(sentence)
    return tuple(merged)
