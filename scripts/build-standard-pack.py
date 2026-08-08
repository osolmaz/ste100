#!/usr/bin/env python3
"""Build the bundled Issue 9 pack from the checked-in exact text."""

from pathlib import Path

from ste100.curate import write_runtime_pack

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = write_runtime_pack(
        ROOT / "docs" / "ASD-STE100_ISSUE9.txt",
        ROOT / "src" / "ste100" / "data" / "issue9",
    )
    counts = manifest.expected_counts
    print(
        f"wrote Issue 9 pack: {counts.approved_words} approved, "
        f"{counts.unapproved_words} unapproved"
    )


if __name__ == "__main__":
    main()
