#!/usr/bin/env python3
"""Fail when the protected-content mutation score is below the project threshold."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

DEFAULT_MINIMUM_SCORE = 80.0
_STATUS_RE = re.compile(r": (killed|survived|timeout)\s*$")


def _run_mutations() -> None:
    completed = subprocess.run(
        ["uv", "run", "mutmut", "run"],
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise subprocess.CalledProcessError(completed.returncode, completed.args)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-only", action="store_true")
    parser.add_argument("--min-kill-rate", type=float, default=DEFAULT_MINIMUM_SCORE)
    args = parser.parse_args()
    if not args.results_only:
        _run_mutations()
    completed = subprocess.run(
        ["uv", "run", "mutmut", "results", "--all", "true"],
        check=True,
        capture_output=True,
        text=True,
    )
    statuses = [_STATUS_RE.search(line) for line in completed.stdout.splitlines()]
    counts = [match.group(1) for match in statuses if match is not None]
    killed = counts.count("killed")
    survived = counts.count("survived")
    timeout = counts.count("timeout")
    total = killed + survived + timeout
    if total == 0:
        print("mutation score unavailable: no mutants were generated", file=sys.stderr)
        return 1
    score = 100.0 * killed / total
    print(
        f"mutation score: {score:.2f}% ({killed}/{total}); survived={survived}, timeout={timeout}"
    )
    if timeout:
        return 1
    return 0 if score >= args.min_kill_rate else 1


if __name__ == "__main__":
    sys.exit(main())
