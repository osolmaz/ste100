"""Load and validate reviewed standard packs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from ste100.models import (
    ConformanceRecord,
    DictionaryEntry,
    ReviewState,
    RuleRecord,
    StandardExample,
    StandardManifest,
)

_REQUIRED_FILES = frozenset({"rules.json", "dictionary.json", "examples.json", "conformance.json"})
_ISSUE9_COUNTS = {
    "numbered_rules": 53,
    "general_rules": 8,
    "approved_words": 875,
    "unapproved_words": 1274,
}


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    path: str | None = None
    severity: Literal["error", "warning"] = "error"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


@dataclass(frozen=True, slots=True)
class StandardPack:
    root: Path
    manifest: StandardManifest
    rules: tuple[RuleRecord, ...]
    dictionary: tuple[DictionaryEntry, ...]
    examples: tuple[StandardExample, ...]
    conformance: tuple[ConformanceRecord, ...]

    @property
    def rules_by_id(self) -> dict[str, RuleRecord]:
        return {rule.rule_id: rule for rule in self.rules}

    @property
    def dictionary_by_word(self) -> dict[str, tuple[DictionaryEntry, ...]]:
        result: dict[str, list[DictionaryEntry]] = {}
        for entry in self.dictionary:
            result.setdefault(entry.word.casefold(), []).append(entry)
            for form in entry.approved_forms:
                result.setdefault(form.casefold(), []).append(entry)
        return {word: tuple(entries) for word, entries in result.items()}


@dataclass(frozen=True, slots=True)
class _Artifacts:
    rules: tuple[RuleRecord, ...]
    dictionary: tuple[DictionaryEntry, ...]
    examples: tuple[StandardExample, ...]
    conformance: tuple[ConformanceRecord, ...]


class StandardValidationError(ValueError):
    """Raised when a standard pack is not safe to load."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        details = "; ".join(f"{issue.code}: {issue.message}" for issue in report.issues)
        super().__init__(details)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _contained_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError("artifact path must be relative")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("artifact path escapes the standard-pack root")
    if not resolved.is_file():
        raise ValueError("artifact path is not a file")
    return resolved


def _read_json(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_model[ModelT: BaseModel](path: Path, model_type: type[ModelT]) -> ModelT:
    return model_type.model_validate(_read_json(path))


def _load_model_list[ModelT: BaseModel](
    path: Path,
    model_type: type[ModelT],
) -> tuple[ModelT, ...]:
    value = _read_json(path)
    if not isinstance(value, list):
        raise ValueError("expected a JSON array")
    return tuple(model_type.model_validate(item) for item in value)


def _add(issues: list[ValidationIssue], code: str, message: str, path: str | None = None) -> None:
    issues.append(ValidationIssue(code=code, message=message, path=path))


def _check_duplicates(
    issues: list[ValidationIssue],
    values: list[str],
    *,
    label: str,
    path: str,
) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            _add(issues, "duplicate_id", f"duplicate {label}: {value}", path)
        seen.add(value)


def _parse_manifest(root: Path, issues: list[ValidationIssue]) -> StandardManifest | None:
    try:
        return _load_model(root / "standard.json", StandardManifest)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _add(issues, "invalid_manifest", str(error), "standard.json")
        return None


def _check_artifact_set(manifest: StandardManifest, issues: list[ValidationIssue]) -> None:
    names = set(manifest.file_digests)
    if names == _REQUIRED_FILES:
        return
    missing = sorted(_REQUIRED_FILES - names)
    extra = sorted(names - _REQUIRED_FILES)
    _add(
        issues,
        "artifact_set",
        f"standard pack artifact set differs; missing={missing}, extra={extra}",
    )


def _resolve_artifacts(
    root: Path,
    manifest: StandardManifest,
    issues: list[ValidationIssue],
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for relative, expected_digest in manifest.file_digests.items():
        try:
            path = _contained_file(root, relative)
        except ValueError as error:
            _add(issues, "unsafe_artifact_path", str(error), relative)
            continue
        paths[relative] = path
        actual_digest = _sha256_file(path)
        if actual_digest != expected_digest:
            _add(
                issues,
                "digest_mismatch",
                f"expected {expected_digest}, got {actual_digest}",
                relative,
            )
    return paths


def _load_artifacts(
    paths: dict[str, Path],
    issues: list[ValidationIssue],
) -> _Artifacts | None:
    if set(paths) != _REQUIRED_FILES:
        return None
    try:
        return _Artifacts(
            rules=_load_model_list(paths["rules.json"], RuleRecord),
            dictionary=_load_model_list(paths["dictionary.json"], DictionaryEntry),
            examples=_load_model_list(paths["examples.json"], StandardExample),
            conformance=_load_model_list(paths["conformance.json"], ConformanceRecord),
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _add(issues, "invalid_artifact", str(error))
        return None


def _check_ids(artifacts: _Artifacts, issues: list[ValidationIssue]) -> None:
    groups = (
        ([rule.rule_id for rule in artifacts.rules], "rule ID", "rules.json"),
        (
            [entry.entry_id for entry in artifacts.dictionary],
            "dictionary entry ID",
            "dictionary.json",
        ),
        (
            [example.example_id for example in artifacts.examples],
            "example ID",
            "examples.json",
        ),
        (
            [item.rule_id for item in artifacts.conformance],
            "conformance rule ID",
            "conformance.json",
        ),
    )
    for values, label, path in groups:
        _check_duplicates(issues, values, label=label, path=path)


def _check_references(artifacts: _Artifacts, issues: list[ValidationIssue]) -> None:
    rule_ids = {rule.rule_id for rule in artifacts.rules}
    dictionary_ids = {
        rule_id
        for entry in artifacts.dictionary
        for meaning in entry.approved_meanings
        for rule_id in meaning.rule_ids
    }
    example_ids = {rule_id for example in artifacts.examples for rule_id in example.rule_ids}
    unknown = sorted((dictionary_ids | example_ids) - rule_ids)
    if unknown:
        _add(issues, "unknown_rule_reference", f"unknown rule IDs: {unknown}")
    if {item.rule_id for item in artifacts.conformance} != rule_ids:
        _add(
            issues,
            "conformance_coverage",
            "conformance records must contain each rule exactly once",
            "conformance.json",
        )


def _check_counts(
    manifest: StandardManifest,
    artifacts: _Artifacts,
    issues: list[ValidationIssue],
) -> None:
    counts = {
        "numbered_rules": sum(not rule.rule_id.startswith("GR-") for rule in artifacts.rules),
        "general_rules": sum(rule.rule_id.startswith("GR-") for rule in artifacts.rules),
        "approved_words": sum(entry.status == "approved" for entry in artifacts.dictionary),
        "unapproved_words": sum(entry.status == "unapproved" for entry in artifacts.dictionary),
    }
    for name, expected in manifest.expected_counts.model_dump().items():
        if counts[name] != expected:
            _add(
                issues,
                "count_mismatch",
                f"{name}: expected {expected}, got {counts[name]}",
            )


def _check_review_state(
    manifest: StandardManifest,
    artifacts: _Artifacts,
    issues: list[ValidationIssue],
) -> None:
    if manifest.review_state is not ReviewState.REVIEWED:
        return
    unreviewed = (
        any(rule.review_state is not ReviewState.REVIEWED for rule in artifacts.rules)
        or any(entry.review_state is not ReviewState.REVIEWED for entry in artifacts.dictionary)
        or any(example.review_state is not ReviewState.REVIEWED for example in artifacts.examples)
    )
    if unreviewed:
        _add(issues, "review_state_mismatch", "a reviewed manifest contains draft records")


def validate_standard_pack(root: Path, *, allow_draft: bool = False) -> ValidationReport:
    """Validate digests, counts, references, review state, and path containment."""

    root = root.resolve()
    issues: list[ValidationIssue] = []
    manifest = _parse_manifest(root, issues)
    if manifest is None:
        return ValidationReport(tuple(issues))
    if manifest.review_state is ReviewState.DRAFT and not allow_draft:
        _add(issues, "draft_pack", "runtime loading requires a reviewed standard pack")
    if manifest.expected_counts.model_dump() != _ISSUE9_COUNTS:
        _add(
            issues,
            "invalid_expected_counts",
            "Issue 9 expected counts must match the published standard counts",
        )
    _check_artifact_set(manifest, issues)
    artifacts = _load_artifacts(_resolve_artifacts(root, manifest, issues), issues)
    if artifacts is not None:
        _check_ids(artifacts, issues)
        _check_references(artifacts, issues)
        _check_counts(manifest, artifacts, issues)
        _check_review_state(manifest, artifacts, issues)
    return ValidationReport(tuple(issues))


def load_standard_pack(root: Path) -> StandardPack:
    """Load a reviewed standard pack only after all validation checks pass."""

    report = validate_standard_pack(root, allow_draft=False)
    if not report.valid:
        raise StandardValidationError(report)
    resolved = root.resolve()
    manifest = _load_model(resolved / "standard.json", StandardManifest)
    return StandardPack(
        root=resolved,
        manifest=manifest,
        rules=_load_model_list(resolved / "rules.json", RuleRecord),
        dictionary=_load_model_list(resolved / "dictionary.json", DictionaryEntry),
        examples=_load_model_list(resolved / "examples.json", StandardExample),
        conformance=_load_model_list(resolved / "conformance.json", ConformanceRecord),
    )
