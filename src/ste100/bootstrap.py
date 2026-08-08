"""Optional spaCy weak-label bootstrapping; never production authority."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol, cast

from ste100.document import char_to_byte_offsets
from ste100.models import ByteRange, ViolationAnnotation


class SpacyToken(Protocol):
    text: str
    idx: int
    dep_: str
    tag_: str


class SpacyDocument(Protocol):
    def __iter__(self) -> Iterator[SpacyToken]: ...


class SpacyPipeline(Protocol):
    def __call__(self, text: str) -> SpacyDocument: ...


def load_spacy_pipeline(model: str = "en_core_web_sm") -> SpacyPipeline:
    """Load an optional spaCy model only when bootstrapping is requested."""

    try:
        import spacy
    except ImportError as error:
        raise RuntimeError("install ste100[spacy] to use weak-label bootstrapping") from error
    return cast(SpacyPipeline, spacy.load(model))


def weak_annotations(text: str, nlp: SpacyPipeline) -> tuple[ViolationAnnotation, ...]:
    """Propose report-only passive-voice and -ing spans for human review."""

    document = nlp(text)
    offsets = char_to_byte_offsets(text)
    annotations: list[ViolationAnnotation] = []
    seen: set[tuple[str, int, int]] = set()
    for token in _iter_tokens(document):
        dep = token.dep_.casefold()
        tag = token.tag_.upper()
        start = token.idx
        token_text = token.text
        end = start + len(token_text)
        if dep in {"nsubjpass", "auxpass"}:
            _append_annotation(
                annotations,
                seen,
                rule_id="3.6",
                start=start,
                end=end,
                offsets=offsets,
            )
        if tag == "VBG":
            _append_annotation(
                annotations,
                seen,
                rule_id="3.5",
                start=start,
                end=end,
                offsets=offsets,
            )
    return tuple(annotations)


def _iter_tokens(document: Iterable[SpacyToken]) -> Iterable[SpacyToken]:
    return document


def _append_annotation(
    annotations: list[ViolationAnnotation],
    seen: set[tuple[str, int, int]],
    *,
    rule_id: str,
    start: int,
    end: int,
    offsets: tuple[int, ...],
) -> None:
    key = (rule_id, start, end)
    if key in seen:
        return
    seen.add(key)
    annotations.append(
        ViolationAnnotation(
            rule_id=rule_id,
            label="uncertain",
            byte_range=ByteRange(start=offsets[start], end=offsets[end]),
            annotator="spacy_weak_bootstrap",
            confidence=None,
        )
    )
