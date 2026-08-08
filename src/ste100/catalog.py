"""Bundled draft rule catalog for explanations and visible coverage."""

from __future__ import annotations

import json
from importlib.resources import files

from pydantic import TypeAdapter

from ste100.models import ConformanceRecord, RuleRecord


def load_rule_catalog() -> tuple[RuleRecord, ...]:
    data = files("ste100.data").joinpath("issue9-rules.json").read_text(encoding="utf-8")
    return TypeAdapter(tuple[RuleRecord, ...]).validate_python(json.loads(data))


def load_conformance_catalog() -> tuple[ConformanceRecord, ...]:
    data = files("ste100.data").joinpath("issue9-conformance.json").read_text(encoding="utf-8")
    return TypeAdapter(tuple[ConformanceRecord, ...]).validate_python(json.loads(data))
