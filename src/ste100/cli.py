"""Offline command-line interface for checking and validating STE100 artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ste100.catalog import load_conformance_catalog
from ste100.checker import analyze
from ste100.dataset import validate_dataset
from ste100.extract import write_draft_extraction
from ste100.models import DatasetRecord, FindingKind
from ste100.standard import (
    StandardPack,
    StandardValidationError,
    ValidationReport,
    load_standard_pack,
    validate_standard_pack,
)
from ste100.terminology import parse_project_dictionary, validate_project_dictionary


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def _report_payload(report: ValidationReport) -> dict[str, object]:
    return {
        "valid": report.valid,
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "path": issue.path,
                "severity": issue.severity,
            }
            for issue in report.issues
        ],
    }


def _load_pack(path: str | None) -> StandardPack | None:
    if path is None:
        return None
    return load_standard_pack(Path(path))


def _validate_standard(args: argparse.Namespace) -> int:
    report = validate_standard_pack(Path(args.pack), allow_draft=args.allow_draft)
    _json(_report_payload(report))
    return 0 if report.valid else 1


def _extract_standard(args: argparse.Namespace) -> int:
    audit = write_draft_extraction(Path(args.source), Path(args.output))
    _json(audit)
    return 0


def _analyze(args: argparse.Namespace) -> int:
    standard = _load_pack(args.standard_pack)
    project = None
    if args.project_dictionary is not None:
        project, report = parse_project_dictionary(Path(args.project_dictionary))
        if project is None or not report.valid:
            _json(_report_payload(report))
            return 2
        if standard is not None:
            report = validate_project_dictionary(project, standard=standard)
            if not report.valid:
                _json(_report_payload(report))
                return 2
    path = Path(args.file)
    text = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")
    result = analyze(text, standard=standard, project_dictionary=project)
    if args.format == "json":
        _json(result.model_dump(mode="json"))
    else:
        print("Unofficial analysis. This result does not certify ASD-STE100 compliance.")
        for finding in result.findings:
            location = (
                "document"
                if finding.byte_range is None
                else f"bytes {finding.byte_range.start}:{finding.byte_range.end}"
            )
            print(f"{finding.kind.value:20} {finding.rule_id:6} {location}: {finding.message}")
        checked = sum(item.status in {"passed", "failed"} for item in result.coverage)
        print(f"Coverage: {checked}/{len(result.coverage)} rules received conclusive checks.")
    return int(any(item.kind is FindingKind.VIOLATION for item in result.findings))


def _validate_project(args: argparse.Namespace) -> int:
    project, report = parse_project_dictionary(Path(args.file))
    if project is not None and report.valid and args.standard_pack is not None:
        standard = load_standard_pack(Path(args.standard_pack))
        report = validate_project_dictionary(project, standard=standard)
    _json(_report_payload(report))
    return 0 if report.valid else 1


def _explain(args: argparse.Namespace) -> int:
    if args.standard_pack is not None:
        standard = load_standard_pack(Path(args.standard_pack))
        rule = standard.rules_by_id.get(args.rule)
        matrix = {item.rule_id: item for item in standard.conformance}
        rule_payload = rule.model_dump(mode="json") if rule is not None else None
    else:
        matrix = {item.rule_id: item for item in load_conformance_catalog()}
        rule_payload = {
            "rule_id": args.rule,
            "requirement": None,
            "review_state": "reviewed_standard_pack_required",
        }
    conformance = matrix.get(args.rule)
    if rule_payload is None or conformance is None:
        print(f"Unknown rule: {args.rule}", file=sys.stderr)
        return 1
    _json(
        {
            "rule": rule_payload,
            "conformance": conformance.model_dump(mode="json"),
            "official_compliance_claimed": False,
        }
    )
    return 0


def _read_dataset(path: Path) -> tuple[DatasetRecord, ...]:
    text = path.read_text(encoding="utf-8")
    adapter = TypeAdapter(tuple[DatasetRecord, ...])
    if path.suffix == ".jsonl":
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        value = json.loads(text)
    return adapter.validate_python(value)


def _validate_dataset(args: argparse.Namespace) -> int:
    try:
        records = _read_dataset(Path(args.file))
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _json(
            {
                "valid": False,
                "issues": [{"code": "invalid_dataset", "message": str(error), "path": args.file}],
            }
        )
        return 1
    report = validate_dataset(records)
    _json(_report_payload(report))
    return 0 if report.valid else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ste100",
        description="Unofficial deterministic ASD-STE100 analysis and data validation.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-standard", help="validate a reviewed standard pack")
    validate.add_argument("pack")
    validate.add_argument("--allow-draft", action="store_true")
    validate.set_defaults(handler=_validate_standard)

    extract = commands.add_parser("extract-standard", help="create review-required Issue 9 drafts")
    extract.add_argument("source")
    extract.add_argument("output")
    extract.set_defaults(handler=_extract_standard)

    analyze_parser = commands.add_parser("analyze", help="analyze a UTF-8 text file")
    analyze_parser.add_argument("file")
    analyze_parser.add_argument("--standard-pack")
    analyze_parser.add_argument("--project-dictionary")
    analyze_parser.add_argument("--format", choices=("text", "json"), default="text")
    analyze_parser.set_defaults(handler=_analyze)

    project = commands.add_parser(
        "validate-project-dictionary",
        help="validate caller-approved technical terminology",
    )
    project.add_argument("file")
    project.add_argument("--standard-pack")
    project.set_defaults(handler=_validate_project)

    explain = commands.add_parser("explain", help="explain one Issue 9 rule and its coverage")
    explain.add_argument("rule")
    explain.add_argument("--standard-pack")
    explain.set_defaults(handler=_explain)

    dataset = commands.add_parser(
        "validate-dataset", help="validate training or evaluation records"
    )
    dataset.add_argument("file")
    dataset.set_defaults(handler=_validate_dataset)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, StandardValidationError, ValidationError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
