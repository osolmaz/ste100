#!/usr/bin/env python3
"""Regenerate checked-in JSON Schemas."""

from pathlib import Path

from ste100.schemas import generate_schemas

if __name__ == "__main__":
    for path in generate_schemas(Path("schemas")):
        print(path)
