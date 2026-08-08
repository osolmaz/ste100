"""Load and validate extracted ASD-STE100 Issue 9 data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ste100.models import DictionaryEntry, RuleRecord, StandardManifest
from ste100.rule_ids import ISSUE9_RULE_ID_SET

_REQUIRED_FILES = frozenset({"rules.json", "dictionary.json"})


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    path: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True, slots=True)
class StandardPack:
    root: Path
    manifest: StandardManifest
    rules: tuple[RuleRecord, ...]
    dictionary: tuple[DictionaryEntry, ...]

    @property
    def rules_by_id(self) -> dict[str, RuleRecord]:
        return {rule.rule_id: rule for rule in self.rules}

    @property
    def dictionary_by_word(self) -> dict[str, tuple[DictionaryEntry, ...]]:
        result: dict[str, list[DictionaryEntry]] = {}
        for entry in self.dictionary:
            expressions = (
                (entry.qualifier,)
                if entry.qualifier is not None
                else (entry.word, *entry.approved_forms)
            )
            for expression in expressions:
                result.setdefault(expression.casefold(), []).append(entry)
        return {word: tuple(entries) for word, entries in result.items()}


@dataclass(frozen=True, slots=True)
class _Artifacts:
    rules: tuple[RuleRecord, ...]
    dictionary: tuple[DictionaryEntry, ...]


class StandardValidationError(ValueError):
    """Raised when extracted standard data is not safe to load."""

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


def _parse_manifest(root: Path, issues: list[ValidationIssue]) -> StandardManifest | None:
    path = root / "standard.json"
    try:
        return _load_model(path, StandardManifest)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _add(issues, "invalid_manifest", str(error), str(path))
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


def _load_artifacts(paths: dict[str, Path], issues: list[ValidationIssue]) -> _Artifacts | None:
    if set(paths) != _REQUIRED_FILES:
        return None
    try:
        return _Artifacts(
            rules=_load_model_list(paths["rules.json"], RuleRecord),
            dictionary=_load_model_list(paths["dictionary.json"], DictionaryEntry),
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _add(issues, "invalid_artifact", str(error))
        return None


def _check_duplicates(
    issues: list[ValidationIssue], values: list[str], *, label: str, path: str
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    for value in sorted(duplicates):
        _add(issues, "duplicate_id", f"duplicate {label}: {value}", path)


def _check_ids(artifacts: _Artifacts, issues: list[ValidationIssue]) -> None:
    _check_duplicates(
        issues,
        [rule.rule_id for rule in artifacts.rules],
        label="rule ID",
        path="rules.json",
    )
    _check_duplicates(
        issues,
        [entry.entry_id for entry in artifacts.dictionary],
        label="dictionary entry ID",
        path="dictionary.json",
    )
    dictionary_keys = [
        f"{entry.status}:{entry.word.casefold()}:{','.join(sorted(set(entry.parts_of_speech)))}"
        for entry in artifacts.dictionary
    ]
    _check_duplicates(
        issues,
        dictionary_keys,
        label="dictionary status/headword/part-of-speech key",
        path="dictionary.json",
    )


def _check_rule_ids(artifacts: _Artifacts, issues: list[ValidationIssue]) -> None:
    rule_ids = {rule.rule_id for rule in artifacts.rules}
    if rule_ids == ISSUE9_RULE_ID_SET:
        return
    missing = sorted(ISSUE9_RULE_ID_SET - rule_ids)
    extra = sorted(rule_ids - ISSUE9_RULE_ID_SET)
    _add(
        issues,
        "rule_catalog",
        f"Issue 9 rule catalog differs; missing={missing}, extra={extra}",
        "rules.json",
    )


def _check_source_digests(
    manifest: StandardManifest,
    artifacts: _Artifacts,
    issues: list[ValidationIssue],
) -> None:
    expected = manifest.source.source_digest
    records: tuple[RuleRecord | DictionaryEntry, ...] = (
        *artifacts.rules,
        *artifacts.dictionary,
    )
    for record in records:
        if record.source.source_digest != expected:
            _add(
                issues,
                "source_digest_mismatch",
                f"record source digest differs from manifest: {record.source.source_digest}",
            )


def validate_standard_pack(root: Path) -> ValidationReport:
    """Validate extracted rules and dictionary data without loading them."""

    issues: list[ValidationIssue] = []
    manifest = _parse_manifest(root, issues)
    if manifest is None:
        return ValidationReport(tuple(issues))
    _check_artifact_set(manifest, issues)
    artifacts = _load_artifacts(_resolve_artifacts(root, manifest, issues), issues)
    if artifacts is not None:
        _check_ids(artifacts, issues)
        _check_rule_ids(artifacts, issues)
        _check_source_digests(manifest, artifacts, issues)
    return ValidationReport(tuple(issues))


def bundled_standard_path() -> Path:
    """Return the installed bundled Issue 9 data path."""

    return Path(str(files("ste100.data").joinpath("issue9")))


@lru_cache(maxsize=1)
def load_bundled_standard() -> StandardPack:
    """Load and cache the bundled Issue 9 data."""

    return load_standard_pack(bundled_standard_path())


def load_standard_pack(root: Path) -> StandardPack:
    """Load extracted standard data after validation passes."""

    report = validate_standard_pack(root)
    if not report.valid:
        raise StandardValidationError(report)
    resolved = root.resolve()
    return StandardPack(
        root=resolved,
        manifest=_load_model(resolved / "standard.json", StandardManifest),
        rules=_load_model_list(resolved / "rules.json", RuleRecord),
        dictionary=_load_model_list(resolved / "dictionary.json", DictionaryEntry),
    )
