from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import BaseModel

from ste100.models import (
    DictionaryEntry,
    RuleRecord,
    SourceLocation,
    StandardManifest,
)
from ste100.rule_ids import ISSUE9_RULE_IDS
from ste100.standard import StandardPack, load_standard_pack

SOURCE_DIGEST = "sha256:" + "0" * 64


def _source(page: int = 1) -> SourceLocation:
    return SourceLocation(
        source_file="ASD-STE100_ISSUE9.txt",
        page=page,
        source_digest=SOURCE_DIGEST,
    )


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def make_standard_pack(root: Path) -> Path:
    root.mkdir()
    rules = [
        RuleRecord(
            rule_id=rule_id,
            requirement=(
                "Use approved words or technical terms."
                if rule_id == "1.1"
                else "Do not use semicolons."
                if rule_id == "8.1"
                else f"Extracted requirement for {rule_id}."
            ),
            source=_source(),
        )
        for rule_id in ISSUE9_RULE_IDS
    ]
    dictionary = [
        DictionaryEntry(
            entry_id="install-v",
            word="install",
            status="approved",
            parts_of_speech=("verb",),
            approved_forms=("installs", "installed"),
            source=_source(),
        ),
        DictionaryEntry(
            entry_id="the-art",
            word="the",
            status="approved",
            parts_of_speech=("article",),
            source=_source(),
        ),
        DictionaryEntry(
            entry_id="utilize-v",
            word="utilize",
            status="unapproved",
            parts_of_speech=("verb",),
            alternatives=("use",),
            source=_source(),
        ),
    ]
    files: dict[str, Sequence[BaseModel]] = {
        "rules.json": rules,
        "dictionary.json": dictionary,
    }
    for name, records in files.items():
        (root / name).write_text(
            json.dumps([record.model_dump(mode="json") for record in records], indent=2) + "\n",
            encoding="utf-8",
        )
    manifest = StandardManifest(
        format_version="1",
        standard_id="ASD-STE100",
        issue=9,
        source=_source(),
        file_digests={name: _digest(root / name) for name in files},
    )
    (root / "standard.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def standard_pack(tmp_path: Path) -> StandardPack:
    return load_standard_pack(make_standard_pack(tmp_path / "standard"))
