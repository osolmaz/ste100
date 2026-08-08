from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ste100.schemas import generate_schemas

_EXPECTED = {
    "analysis.schema.json",
    "dictionary.schema.json",
    "project-dictionary.schema.json",
    "rules.schema.json",
    "standard.schema.json",
}


def test_schema_generator_writes_only_deterministic_contracts(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "schemas"
    output.mkdir(parents=True)
    stale = output / "conformance.schema.json"
    stale.write_text("{}\n", encoding="utf-8")
    paths = generate_schemas(output)
    assert not stale.exists()
    assert {path.name for path in paths} == _EXPECTED
    assert all(path.parent == output for path in paths)
    assert all(path.read_text(encoding="utf-8").endswith("\n") for path in paths)
    for path in paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] in {"array", "object"}


def test_schema_generation_has_registered_bytes(tmp_path: Path) -> None:
    paths = generate_schemas(tmp_path / "nested" / "schemas")
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    assert digest.hexdigest() == "fbe943249bd5a900d651ab3b56ce9f208bf9b23060d69f4439c166eae2238ce9"


def test_schema_generation_is_byte_reproducible_and_repeatable(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_schemas(first)
    first_bytes = {name: (first / name).read_bytes() for name in _EXPECTED}
    generate_schemas(first)
    generate_schemas(second)
    for name in _EXPECTED:
        assert (first / name).read_bytes() == first_bytes[name]
        assert (second / name).read_bytes() == first_bytes[name]
