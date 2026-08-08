#!/usr/bin/env python3
"""Verify that a built wheel contains the deterministic runtime pack."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

_REQUIRED = {
    "ste100/data/issue9/dictionary.json",
    "ste100/data/issue9/rules.json",
    "ste100/data/issue9/standard.json",
}
_FORBIDDEN_MODULES = {
    "ste100/bootstrap.py",
    "ste100/contracts.py",
    "ste100/dataset.py",
    "ste100/model_release.py",
    "ste100/protection.py",
    "ste100/rewrite.py",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    wheels = tuple(args.dist.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one wheel, found {len(wheels)}")
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        missing = sorted(_REQUIRED - names)
        forbidden = sorted(_FORBIDDEN_MODULES & names)
        if missing or forbidden:
            raise RuntimeError(f"wheel contents differ; missing={missing}, forbidden={forbidden}")
        if any(
            name in names
            for name in (
                "ste100/data/issue9/conformance.json",
                "ste100/data/issue9/examples.json",
            )
        ):
            raise RuntimeError("wheel contains removed result-model artifacts")
        if archive.getinfo("ste100/data/issue9/dictionary.json").file_size < 1_000_000:
            raise RuntimeError("bundled dictionary is unexpectedly small")
    print(f"wheel check passed: {wheels[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
