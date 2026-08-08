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


def test_dataset_distinguishes_overlapping_protected_values() -> None:
    ten = ProtectedSpan(
        span_id="span_3333333333333333",
        kind="number",
        byte_range=ByteRange(start=0, end=2),
        text_digest=_digest("10"),
    )
    hundred = ProtectedSpan(
        span_id="span_4444444444444444",
        kind="number",
        byte_range=ByteRange(start=3, end=6),
        text_digest=_digest("100"),
    )
    record = _record(
        source_kind="technical_document",
        source_id="overlap",
        text="10 100",
        protected_spans=(ten, hundred),
        target_text="Keep 10 and 100.",
    )
    assert validate_dataset((record,)).valid


def test_dataset_rejects_protected_value_embedded_in_modified_number() -> None:
    measurement = ProtectedSpan(
        span_id="span_7777777777777777",
        kind="unit",
        byte_range=ByteRange(start=0, end=5),
        text_digest=_digest("10 mm"),
    )
    record = _record(
        source_kind="technical_document",
        source_id="changed-number",
        text="10 mm",
        protected_spans=(measurement,),
        target_text="Use 110 mm.",
    )
    codes = {issue.code for issue in validate_dataset((record,)).issues}
    assert "protected_target" in codes


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


def test_dataset_rejects_violation_annotated_standard_parent() -> None:
    parent = _record(
        source_kind="standard_example",
        source_id="negative-standard",
        text="Bad example.",
    ).model_copy(
        update={
            "annotations": (
                ViolationAnnotation(
                    rule_id="8.1",
                    label="violation",
                    annotator="reviewer",
                ),
            )
        }
    )
    child = _record(
        source_kind="synthetic",
        source_id="from-negative",
        text="Generated example.",
        parent_record_ids=(parent.record_id,),
    )
    codes = {issue.code for issue in validate_dataset((parent, child)).issues}
    assert "unclean_synthetic_parent" in codes


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


def test_dataset_uses_source_order_not_protected_array_order() -> None:
    first = ProtectedSpan(
        span_id="span_5555555555555555",
        kind="identifier",
        byte_range=ByteRange(start=0, end=4),
        text_digest=_digest("ID_A"),
    )
    second = ProtectedSpan(
        span_id="span_6666666666666666",
        kind="identifier",
        byte_range=ByteRange(start=5, end=9),
        text_digest=_digest("ID_B"),
    )
    valid = _record(
        source_kind="technical_document",
        source_id="source-order",
        text="ID_A ID_B",
        protected_spans=(second, first),
        target_text="Keep ID_A ID_B.",
    )
    assert validate_dataset((valid,)).valid

    reversed_target = valid.model_copy(update={"target_text": "Keep ID_B ID_A."})
    codes = {issue.code for issue in validate_dataset((reversed_target,)).issues}
    assert "protected_order" in codes


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


def test_synthetic_child_must_remain_in_parent_split() -> None:
    parent = _record(
        source_kind="standard_example",
        source_id="train-parent",
        text="Clean source.",
        split="train",
        group="parent-group",
    )
    child = _record(
        source_kind="synthetic",
        source_id="test-child",
        text="Generated child.",
        split="test",
        group="child-group",
        parent_record_ids=(parent.record_id,),
    )
    codes = {issue.code for issue in validate_dataset((parent, child)).issues}
    assert "synthetic_split_leakage" in codes


def test_synthetic_provenance_rejects_self_and_mutual_cycles() -> None:
    self_parent = _record(
        source_kind="synthetic",
        source_id="self",
        text="Self parent.",
    )
    self_parent = self_parent.model_copy(update={"parent_record_ids": (self_parent.record_id,)})
    assert "cyclic_provenance" in {issue.code for issue in validate_dataset((self_parent,)).issues}

    first = _record(source_kind="synthetic", source_id="cycle-a", text="Cycle A.")
    second = _record(source_kind="synthetic", source_id="cycle-b", text="Cycle B.")
    first = first.model_copy(update={"parent_record_ids": (second.record_id,)})
    second = second.model_copy(update={"parent_record_ids": (first.record_id,)})
    cyclic = [
        issue
        for issue in validate_dataset((first, second)).issues
        if issue.code == "cyclic_provenance"
    ]
    assert {issue.path for issue in cyclic} == {first.record_id, second.record_id}


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
