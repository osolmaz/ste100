#!/usr/bin/env python3
"""Exercise STE100 foundations on private response-style records without printing prose."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ste100.checker import analyze


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--limit", type=int)
    return parser


def _check_response(value: str) -> int:
    result = analyze(value)
    encoded = value.encode("utf-8")
    for finding in result.findings:
        excerpt = encoded[finding.byte_range.start : finding.byte_range.end].decode("utf-8")
        if excerpt != finding.excerpt:
            raise RuntimeError("finding offsets did not preserve source text")
    if result.passed is bool(result.findings):
        raise RuntimeError("passed does not match findings")
    return len(result.findings)


def main() -> int:
    args = _parser().parse_args()
    path = args.dataset / "examples.jsonl" if args.dataset.is_dir() else args.dataset
    records = 0
    responses = 0
    revision_pairs = 0
    deterministic_findings = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if args.limit is not None and records >= args.limit:
                break
            record = json.loads(line)
            records += 1
            values = [record.get("initial_assistant_response")]
            final = record.get("final_assistant_response")
            if final:
                values.append(final)
                revision_pairs += 1
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    continue
                deterministic_findings += _check_response(value)
                responses += 1
    print(
        json.dumps(
            {
                "records_checked": records,
                "responses_checked": responses,
                "revision_pairs_checked": revision_pairs,
                "deterministic_findings": deterministic_findings,
                "private_content_printed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
