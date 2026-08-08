"""Bundled reviewed-independent Issue 9 conformance metadata."""

from __future__ import annotations

import json
from importlib.resources import files

from pydantic import TypeAdapter

from ste100.models import ConformanceRecord


def load_conformance_catalog() -> tuple[ConformanceRecord, ...]:
    data = files("ste100.data").joinpath("issue9-conformance.json").read_text(encoding="utf-8")
    return TypeAdapter(tuple[ConformanceRecord, ...]).validate_python(json.loads(data))
