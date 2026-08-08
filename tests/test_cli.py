from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import make_standard_pack
from ste100.cli import main


def test_cli_analyze_json_and_text(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.txt"
    source.write_text("Don't continue; stop.", encoding="utf-8")

    assert main(["analyze", str(source), "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["official_compliance_claimed"] is False
    rule_ids = {item["rule_id"] for item in payload["findings"]}
    assert {"4.2", "8.1"} <= rule_ids

    assert main(["analyze", str(source)]) == 1
    output = capsys.readouterr().out
    assert "does not certify" in output
    assert "Coverage:" in output


def test_cli_validates_pack_and_explains_bundled_rule(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack = make_standard_pack(tmp_path / "pack")
    assert main(["validate-standard", str(pack)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True

    assert main(["explain", "8.1"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["rule"]["rule_id"] == "8.1"
    assert "semicolon" in payload["rule"]["requirement"]
    assert payload["rule"]["review_state"] == "reviewed"
    assert payload["conformance"]["coverage_scope"] == "full"

    assert main(["explain", "8.1", "--standard-pack", str(pack)]) == 0
    reviewed = json.loads(capsys.readouterr().out)
    assert reviewed["rule"]["requirement"] == "Do not use semicolons."

    assert main(["explain", "99.1"]) == 1
    assert "Unknown rule" in capsys.readouterr().err


def test_cli_analyzes_with_reviewed_pack_and_project_dictionary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack = make_standard_pack(tmp_path / "pack")
    project = tmp_path / "project.json"
    project.write_text(
        json.dumps(
            {
                "format_version": "1",
                "terms": [
                    {
                        "term": "fuel pump",
                        "category": "technical_noun",
                        "meaning": "A pump for fuel",
                        "source": "project glossary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source = tmp_path / "input.txt"
    source.write_text("Install the fuel pump.", encoding="utf-8")
    assert (
        main(
            [
                "analyze",
                str(source),
                "--standard-pack",
                str(pack),
                "--project-dictionary",
                str(project),
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["findings"] == []


def test_cli_rejects_invalid_project_dictionary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "project.json"
    project.write_text('{"format_version":"1","terms":[{"term":"x"}]}', encoding="utf-8")
    assert main(["validate-project-dictionary", str(project)]) == 1
    assert json.loads(capsys.readouterr().out)["valid"] is False


def test_cli_runs_pinned_spacy_checks(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "procedure.txt"
    source.write_text("1. The access panel is opened.", encoding="utf-8")
    assert main(["analyze", str(source), "--spacy", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert {item["rule_id"] for item in payload["findings"]} >= {"3.6", "5.3"}


def test_cli_extracts_a_valid_runtime_pack(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "issue9"
    assert main(["extract-standard", "docs/ASD-STE100_ISSUE9.txt", str(output)]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["review_state"] == "reviewed"
    assert manifest["expected_counts"]["approved_words"] == 876
    assert main(["validate-standard", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_cli_returns_configuration_error_for_missing_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["analyze", "/does/not/exist"]) == 2
    assert "No such file" in capsys.readouterr().err
