from __future__ import annotations

import hashlib
from typing import Literal

import pytest
from pydantic import ValidationError

from ste100.dataset import record_id_for, validate_dataset
from ste100.models import (
    ByteRange,
    DatasetRecord,
    ProtectedSpan,
    SplitMembership,
    ViolationAnnotation,
)

_SOURCE_DIGEST = "sha256:" + "1" * 64


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _record(
    *,
    source_kind: Literal[
        "standard_example",
        "technical_document",
        "conversation_revision",
        "synthetic",
    ],
    source_id: str,
    text: str,
    split: Literal["train", "validation", "test", "sealed_test"] = "train",
    group: str = "document-1",
    parent_record_ids: tuple[str, ...] = (),
    protected_spans: tuple[ProtectedSpan, ...] = (),
    target_text: str | None = None,
    annotation_state: Literal["weak", "reviewed", "adjudicated"] = "reviewed",
) -> DatasetRecord:
    return DatasetRecord(
        record_id=record_id_for(
            source_kind=source_kind,
            source_id=source_id,
            source_digest=_SOURCE_DIGEST,
            text=text,
        ),
        source_kind=source_kind,
        source_id=source_id,
        source_digest=_SOURCE_DIGEST,
        parent_record_ids=parent_record_ids,
        text=text,
        rule_ids=("8.1",),
        annotations=(
            ViolationAnnotation(
                rule_id="8.1",
                label="no_violation",
                annotator="reviewer",
            ),
        ),
        protected_spans=protected_spans,
        split=SplitMembership(
            split=split,
            group_id=group,
            model_family="family-a",
            time_bucket="2026-08",
        ),
        annotation_state=annotation_state,
        target_text=target_text,
    )


def test_valid_dataset_keeps_synthetic_provenance_and_protected_content() -> None:
    parent = _record(
        source_kind="standard_example",
        source_id="standard-1",
        text="Install UNIT_A.",
    )
    protected = ProtectedSpan(
        span_id="span_0123456789abcdef",
        kind="identifier",
        byte_range=ByteRange(start=8, end=14),
        text_digest=_digest("UNIT_A"),
    )
    synthetic = _record(
        source_kind="synthetic",
        source_id="synthetic-1",
        text="Install UNIT_A now.",
        parent_record_ids=(parent.record_id,),
        protected_spans=(protected,),
        target_text="Now install UNIT_A.",
    )

    report = validate_dataset((parent, synthetic))
    assert report.valid
    assert report.issues == ()


def test_dataset_allows_repeated_protected_value_when_count_and_order_match() -> None:
    first = ProtectedSpan(
        span_id="span_1111111111111111",
        kind="identifier",
        byte_range=ByteRange(start=0, end=4),
        text_digest=_digest("ID_A"),
    )
    second = ProtectedSpan(
        span_id="span_2222222222222222",
        kind="identifier",
        byte_range=ByteRange(start=9, end=13),
        text_digest=_digest("ID_A"),
    )
    record = _record(
        source_kind="technical_document",
        source_id="repeated",
        text="ID_A and ID_A",
        protected_spans=(first, second),
        target_text="Keep ID_A and ID_A.",
    )
    assert validate_dataset((record,)).valid


def test_dataset_detects_group_source_family_time_and_text_leakage() -> None:
    train = _record(source_kind="technical_document", source_id="doc", text="Same text.")
    test = _record(
        source_kind="technical_document",
        source_id="doc",
        text="Same text.",
        split="test",
        group="document-1",
    )
    report = validate_dataset((train, test))

    leakage = [issue for issue in report.issues if issue.code == "split_leakage"]
    assert len(leakage) == 5


def test_dataset_rejects_bad_id_digest_range_and_unreviewed_synthetic_parent() -> None:
    parent = _record(
        source_kind="technical_document",
        source_id="parent",
        text="Bad source.",
        annotation_state="weak",
    )
    span = ProtectedSpan(
        span_id="span_0123456789abcdef",
        kind="identifier",
        byte_range=ByteRange(start=0, end=3),
        text_digest="sha256:" + "f" * 64,
    )
    child = _record(
        source_kind="synthetic",
        source_id="child",
        text="Bad target.",
        parent_record_ids=(parent.record_id,),
        protected_spans=(span,),
        target_text="Different.",
    ).model_copy(update={"record_id": "record_0123456789abcdef"})

    codes = {issue.code for issue in validate_dataset((parent, child)).issues}
    assert {
        "record_id_mismatch",
        "protected_digest",
        "protected_target",
        "unclean_synthetic_parent",
    }.issubset(codes)


def test_dataset_rejects_annotation_that_splits_utf8_character() -> None:
    record = _record(
        source_kind="technical_document",
        source_id="unicode",
        text="é text",
    ).model_copy(
        update={
            "annotations": (
                ViolationAnnotation(
                    rule_id="8.1",
                    label="violation",
                    byte_range=ByteRange(start=1, end=2),
                    annotator="reviewer",
                ),
            )
        }
    )
    report = validate_dataset((record,))
    assert "annotation_range" in {issue.code for issue in report.issues}


def test_dataset_rejects_missing_parent_and_reordered_protected_values() -> None:
    first = ProtectedSpan(
        span_id="span_1111111111111111",
        kind="identifier",
        byte_range=ByteRange(start=0, end=4),
        text_digest=_digest("ID_A"),
    )
    second = ProtectedSpan(
        span_id="span_2222222222222222",
        kind="identifier",
        byte_range=ByteRange(start=5, end=9),
        text_digest=_digest("ID_B"),
    )
    record = _record(
        source_kind="synthetic",
        source_id="reordered",
        text="ID_A ID_B",
        parent_record_ids=("record_ffffffffffffffff",),
        protected_spans=(first, second),
        target_text="ID_B ID_A",
    )
    codes = {issue.code for issue in validate_dataset((record,)).issues}
    assert {"missing_parent", "protected_order"}.issubset(codes)


def test_conversation_outcome_cannot_be_inferred_from_silence() -> None:
    common = {
        "record_id": "record_0123456789abcdef",
        "source_kind": "conversation_revision",
        "source_id": "conversation-1",
        "source_digest": _SOURCE_DIGEST,
        "text": "A response.",
        "split": {"split": "train", "group_id": "conversation-1"},
        "annotation_state": "weak",
    }
    with pytest.raises(ValidationError, match="observed outcome"):
        DatasetRecord.model_validate(common)
    with pytest.raises(ValidationError):
        DatasetRecord.model_validate(
            {**common, "observed_outcome": "continued_without_revision", "inferred_approval": True}
        )
