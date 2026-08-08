"""Independent detector and rewriter release-manifest validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ste100.models import ModelManifest
from ste100.standard import ValidationIssue, ValidationReport

_REQUIRED_THRESHOLDS = {
    "detector": frozenset({"rule_macro_f1", "span_f1", "calibration_error"}),
    "rewriter": frozenset(
        {"meaning_preservation", "protected_content_accuracy", "deterministic_non_regression"}
    ),
}


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return f"sha256:{value.hexdigest()}"


def validate_model_release(
    manifest: ModelManifest,
    *,
    artifact: Path,
    evaluation: Path,
) -> ValidationReport:
    """Check immutable artifacts and role-specific release evidence."""

    issues: list[ValidationIssue] = []
    for label, path, expected in (
        ("artifact", artifact, manifest.artifact_digest),
        ("evaluation", evaluation, manifest.evaluation_digest),
    ):
        if not path.is_file():
            issues.append(
                ValidationIssue(code="missing_release_file", message=f"missing {label}: {path}")
            )
            continue
        actual = _digest(path)
        if actual != expected:
            issues.append(
                ValidationIssue(
                    code="release_digest",
                    message=f"{label} digest mismatch: expected {expected}, got {actual}",
                    path=str(path),
                )
            )
    required = _REQUIRED_THRESHOLDS[manifest.role]
    missing = sorted(required - set(manifest.thresholds))
    if missing:
        issues.append(
            ValidationIssue(
                code="release_thresholds",
                message=f"missing role-specific thresholds: {missing}",
            )
        )
    if manifest.pretraining_contamination == "unknown":
        issues.append(
            ValidationIssue(
                code="pretraining_contamination",
                message=(
                    "pretraining contamination is unknown and must be disclosed "
                    "in evaluation reports"
                ),
                severity="warning",
            )
        )
    return ValidationReport(tuple(issues))
