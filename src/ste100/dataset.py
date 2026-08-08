"""Dataset identity, provenance, protection, and leakage validation."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from itertools import pairwise

from ste100.document import slice_bytes
from ste100.models import DatasetRecord, ProtectedSpan
from ste100.standard import ValidationIssue, ValidationReport


def record_id_for(
    *,
    source_kind: str,
    source_id: str,
    source_digest: str,
    text: str,
) -> str:
    """Create a deterministic record ID without exposing source text."""

    payload = "\0".join((source_kind, source_id, source_digest, text)).encode("utf-8")
    return f"record_{hashlib.sha256(payload).hexdigest()[:16]}"


def _digest(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _issue(
    issues: list[ValidationIssue],
    code: str,
    message: str,
    record_id: str | None = None,
) -> None:
    issues.append(ValidationIssue(code=code, message=message, path=record_id))


def _check_identity_and_annotations(
    record: DatasetRecord,
    issues: list[ValidationIssue],
) -> None:
    expected_id = record_id_for(
        source_kind=record.source_kind,
        source_id=record.source_id,
        source_digest=record.source_digest,
        text=record.text,
    )
    if record.record_id != expected_id:
        _issue(
            issues,
            "record_id_mismatch",
            f"expected deterministic ID {expected_id}",
            record.record_id,
        )
    annotation_rules = {annotation.rule_id for annotation in record.annotations}
    if not annotation_rules.issubset(set(record.rule_ids)):
        _issue(
            issues,
            "annotation_rule_missing",
            "every annotation rule must occur in rule_ids",
            record.record_id,
        )
    text_size = len(record.text.encode("utf-8"))
    for annotation in record.annotations:
        byte_range = annotation.byte_range
        if byte_range is None:
            continue
        if byte_range.end > text_size:
            _issue(
                issues,
                "annotation_range",
                "annotation range is outside source text",
                record.record_id,
            )
            continue
        try:
            slice_bytes(record.text, byte_range)
        except ValueError as error:
            _issue(issues, "annotation_range", str(error), record.record_id)


def _protected_original(
    record: DatasetRecord,
    span: ProtectedSpan,
    issues: list[ValidationIssue],
) -> str | None:
    if span.byte_range.end > len(record.text.encode("utf-8")):
        _issue(
            issues, "protected_range", "protected range is outside source text", record.record_id
        )
        return None
    try:
        original = slice_bytes(record.text, span.byte_range)
    except ValueError as error:
        _issue(issues, "protected_range", str(error), record.record_id)
        return None
    if _digest(original) != span.text_digest:
        _issue(
            issues,
            "protected_digest",
            "protected text digest does not match the source slice",
            record.record_id,
        )
    return original


def _check_target_values(
    record: DatasetRecord,
    originals: list[str],
    issues: list[ValidationIssue],
) -> None:
    if record.target_text is None or not originals:
        return
    alternatives = sorted(set(originals), key=lambda value: (-len(value), value))
    pattern = re.compile("|".join(re.escape(value) for value in alternatives))
    occurrences = [match.group() for match in pattern.finditer(record.target_text)]
    if Counter(occurrences) != Counter(originals):
        _issue(
            issues,
            "protected_target",
            "target must preserve the count of each protected source value",
            record.record_id,
        )
        return
    if occurrences != originals:
        _issue(
            issues,
            "protected_order",
            "target changes the order of protected source values",
            record.record_id,
        )


def _check_record(record: DatasetRecord, issues: list[ValidationIssue]) -> None:
    _check_identity_and_annotations(record, issues)
    ordered_spans = tuple(
        sorted(
            record.protected_spans, key=lambda span: (span.byte_range.start, span.byte_range.end)
        )
    )
    if any(
        current.byte_range.start < previous.byte_range.end
        for previous, current in pairwise(ordered_spans)
    ):
        _issue(
            issues,
            "protected_overlap",
            "protected source spans overlap",
            record.record_id,
        )
    originals = [
        original
        for span in ordered_spans
        if (original := _protected_original(record, span, issues)) is not None
    ]
    _check_target_values(record, originals, issues)
    if record.source_kind == "synthetic" and not record.parent_record_ids:
        _issue(
            issues,
            "synthetic_parent",
            "synthetic records require a reviewed clean-source parent",
            record.record_id,
        )


def _split_maps(items: tuple[DatasetRecord, ...]) -> dict[str, dict[object, set[str]]]:
    maps: dict[str, dict[object, set[str]]] = {
        label: defaultdict(set)
        for label in ("group", "source", "model_family", "time_bucket", "text")
    }
    for record in items:
        split = record.split.split
        maps["group"][record.split.group_id].add(split)
        maps["source"][(record.source_kind, record.source_id)].add(split)
        maps["text"][_digest(record.text)].add(split)
        if record.split.model_family is not None:
            maps["model_family"][record.split.model_family].add(split)
        if record.split.time_bucket is not None:
            maps["time_bucket"][record.split.time_bucket].add(split)
    return maps


def _check_split_leakage(
    items: tuple[DatasetRecord, ...],
    issues: list[ValidationIssue],
) -> None:
    for label, mapping in _split_maps(items).items():
        for key, splits in mapping.items():
            if len(splits) > 1:
                _issue(
                    issues,
                    "split_leakage",
                    f"{label} {key!r} occurs in multiple splits: {sorted(splits)}",
                )


def _parent_is_clean(parent: DatasetRecord) -> bool:
    clean_annotations = bool(parent.annotations) and all(
        annotation.label in {"no_violation", "exception"} for annotation in parent.annotations
    )
    standard_positive = (
        parent.source_kind == "standard_example"
        and parent.annotation_state in {"reviewed", "adjudicated"}
        and clean_annotations
    )
    reviewed_clean = parent.annotation_state == "adjudicated" and clean_annotations
    return standard_positive or reviewed_clean


def _check_parents(
    items: tuple[DatasetRecord, ...],
    by_id: dict[str, DatasetRecord],
    issues: list[ValidationIssue],
) -> None:
    for record in items:
        for parent_id in record.parent_record_ids:
            parent = by_id.get(parent_id)
            if parent is None:
                _issue(
                    issues,
                    "missing_parent",
                    f"parent record does not exist: {parent_id}",
                    record.record_id,
                )
            elif not _parent_is_clean(parent):
                _issue(
                    issues,
                    "unclean_synthetic_parent",
                    (
                        "synthetic parent must be a reviewed standard example "
                        "or adjudicated clean text"
                    ),
                    record.record_id,
                )
            elif record.source_kind == "synthetic" and record.split.split != parent.split.split:
                _issue(
                    issues,
                    "synthetic_split_leakage",
                    "synthetic child and parent must use the same split",
                    record.record_id,
                )


def validate_dataset(records: Iterable[DatasetRecord]) -> ValidationReport:
    """Validate deterministic IDs, complete-group splits, and protected content."""

    items = tuple(records)
    issues: list[ValidationIssue] = []
    by_id: dict[str, DatasetRecord] = {}
    for record in items:
        if record.record_id in by_id:
            _issue(issues, "duplicate_record", "duplicate record ID", record.record_id)
        by_id[record.record_id] = record
        _check_record(record, issues)
    _check_split_leakage(items, issues)
    _check_parents(items, by_id, issues)
    return ValidationReport(tuple(issues))
