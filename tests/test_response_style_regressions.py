from __future__ import annotations

import json
from pathlib import Path

from ste100.checker import analyze


def test_sanitized_response_style_pairs_keep_brevity_separate_from_ste() -> None:
    records = json.loads(
        Path("tests/fixtures/sanitized-response-style.json").read_text(encoding="utf-8")
    )
    first, second = records

    assert len(first["final_assistant_response"].split()) < len(
        first["initial_assistant_response"].split()
    )
    assert analyze(first["initial_assistant_response"]).findings == ()
    assert analyze(first["final_assistant_response"]).findings == ()

    initial = analyze(second["initial_assistant_response"])
    final = analyze(second["final_assistant_response"])
    assert initial.findings == ()
    assert [(finding.rule_id, finding.excerpt) for finding in final.findings] == [("8.1", ";")]
