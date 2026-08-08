"""Generate portable JSON Schemas from the authoritative Pydantic contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from ste100.models import (
    AnalysisResult,
    ConformanceRecord,
    DictionaryEntry,
    ProjectDictionary,
    RuleRecord,
    StandardExample,
    StandardManifest,
)

_SCHEMA_TYPES: dict[str, Any] = {
    "standard.schema.json": StandardManifest,
    "rules.schema.json": list[RuleRecord],
    "dictionary.schema.json": list[DictionaryEntry],
    "examples.schema.json": list[StandardExample],
    "conformance.schema.json": list[ConformanceRecord],
    "project-dictionary.schema.json": ProjectDictionary,
    "analysis.schema.json": AnalysisResult,
}


def generate_schemas(output_dir: Path) -> tuple[Path, ...]:
    """Write deterministic Draft 2020-12 JSON Schema documents."""

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model_type in sorted(_SCHEMA_TYPES.items()):
        schema = TypeAdapter(model_type).json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        path = output_dir / filename
        path.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return tuple(written)
