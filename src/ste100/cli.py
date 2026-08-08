"""Offline command-line interface for checking and validating STE100 artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from ste100.checker import analyze
from ste100.curate import write_runtime_pack
from ste100.linguistics import SpacyAnalyzer
from ste100.standard import (
    StandardPack,
    StandardValidationError,
    ValidationReport,
    load_bundled_standard,
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
            }
            for issue in report.issues
        ],
    }


def _load_pack(path: str | None) -> StandardPack:
    if path is None:
        return load_bundled_standard()
    return load_standard_pack(Path(path))


def _validate_standard(args: argparse.Namespace) -> int:
    report = validate_standard_pack(Path(args.pack))
    _json(_report_payload(report))
    return 0 if report.valid else 1


def _extract_standard(args: argparse.Namespace) -> int:
    manifest = write_runtime_pack(Path(args.source), Path(args.output))
    _json(manifest.model_dump(mode="json"))
    return 0


def _analyze(args: argparse.Namespace) -> int:
    standard = _load_pack(args.standard_pack)
    project = None
    if args.project_dictionary is not None:
        project, report = parse_project_dictionary(Path(args.project_dictionary))
        if project is None or not report.valid:
            _json(_report_payload(report))
            return 2
        report = validate_project_dictionary(project)
        if not report.valid:
            _json(_report_payload(report))
            return 2
    path = Path(args.file)
    text = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")
    analyzer = SpacyAnalyzer() if args.spacy else None
    result = analyze(
        text,
        standard=standard,
        project_dictionary=project,
        linguistic_analyzer=analyzer,
    )
    if args.format == "json":
        _json(result.model_dump(mode="json"))
    else:
        print("PASS" if result.passed else "FAIL")
        for finding in result.findings:
            rules = ", ".join(finding.rule_ids)
            location = f"bytes {finding.byte_range.start}:{finding.byte_range.end}"
            print(f"Rules {rules} {location}: {finding.message}")
    return int(not result.passed)


def _validate_project(args: argparse.Namespace) -> int:
    project, report = parse_project_dictionary(Path(args.file))
    if project is not None and report.valid:
        report = validate_project_dictionary(project)
    _json(_report_payload(report))
    return 0 if report.valid else 1


def _explain(args: argparse.Namespace) -> int:
    standard = _load_pack(args.standard_pack)
    rule = standard.rules_by_id.get(args.rule)
    if rule is None:
        print(f"Unknown rule: {args.rule}", file=sys.stderr)
        return 1
    _json(rule.model_dump(mode="json"))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ste100",
        description="Check text with source-backed ASD-STE100 Issue 9 checks.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.2.0")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-standard", help="validate extracted standard data")
    validate.add_argument("pack")
    validate.set_defaults(handler=_validate_standard)

    extract = commands.add_parser("extract-standard", help="build a source-traceable Issue 9 pack")
    extract.add_argument("source")
    extract.add_argument("output")
    extract.set_defaults(handler=_extract_standard)

    analyze_parser = commands.add_parser("analyze", help="analyze a UTF-8 text file")
    analyze_parser.add_argument("file")
    analyze_parser.add_argument("--standard-pack")
    analyze_parser.add_argument("--project-dictionary")
    analyze_parser.add_argument("--spacy", action="store_true")
    analyze_parser.add_argument("--format", choices=("text", "json"), default="text")
    analyze_parser.set_defaults(handler=_analyze)

    project = commands.add_parser(
        "validate-project-dictionary",
        help="validate caller-approved technical terminology",
    )
    project.add_argument("file")
    project.set_defaults(handler=_validate_project)

    explain = commands.add_parser("explain", help="show one extracted Issue 9 requirement")
    explain.add_argument("rule")
    explain.add_argument("--standard-pack")
    explain.set_defaults(handler=_explain)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (
        OSError,
        RuntimeError,
        StandardValidationError,
        ValidationError,
        json.JSONDecodeError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
