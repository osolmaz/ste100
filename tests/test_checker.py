from __future__ import annotations

import pytest

from ste100.checker import analyze
from ste100.contracts import DetectorPrediction, StaticDetector
from ste100.models import (
    ByteRange,
    CoverageStatus,
    FindingKind,
    ProjectDictionary,
    ProjectTerm,
)
from ste100.standard import StandardPack


def _project_dictionary() -> ProjectDictionary:
    return ProjectDictionary(
        format_version="1",
        terms=(
            ProjectTerm(
                term="fuel pump",
                category="technical_noun",
                meaning="A pump that moves fuel",
                source="project glossary",
            ),
        ),
    )


def test_semicolon_and_contraction_are_exact_findings() -> None:
    result = analyze("Don't remove the cover; it won\u2019t move.")
    pairs = {(finding.rule_id, finding.excerpt) for finding in result.findings}
    assert ("4.2", "Don't") in pairs
    assert ("4.2", "won\u2019t") in pairs
    assert ("8.1", ";") in pairs
    assert result.official_compliance_claimed is False
    assert len(result.coverage) == 61


def test_vocabulary_uses_reviewed_dictionary_and_project_terms(
    standard_pack: StandardPack,
) -> None:
    result = analyze(
        "Utilize the fuel pump.",
        standard=standard_pack,
        project_dictionary=_project_dictionary(),
    )
    violations = [item for item in result.findings if item.kind is FindingKind.VIOLATION]
    reviews = [item for item in result.findings if item.kind is FindingKind.HUMAN_REVIEW]

    assert [(item.rule_id, item.excerpt) for item in violations] == [("1.1", "Utilize")]
    assert reviews == []
    assert "Use: use." in violations[0].message


def test_unknown_vocabulary_is_human_review_not_a_violation(
    standard_pack: StandardPack,
) -> None:
    result = analyze("Install the widget.", standard=standard_pack)
    widget = next(item for item in result.findings if item.excerpt == "widget")
    coverage = next(item for item in result.coverage if item.rule_id == "1.1")

    assert widget.kind is FindingKind.HUMAN_REVIEW
    assert coverage.status is CoverageStatus.HUMAN_REVIEW


def test_analyze_rejects_ambiguous_project_dictionary() -> None:
    project = ProjectDictionary(
        format_version="1",
        terms=(
            ProjectTerm(
                term="first term",
                category="technical_noun",
                approved_forms=("shared",),
                meaning="First",
                source="test",
            ),
            ProjectTerm(
                term="second term",
                category="technical_noun",
                approved_forms=("SHARED",),
                meaning="Second",
                source="test",
            ),
        ),
    )
    with pytest.raises(ValueError, match="invalid project dictionary"):
        analyze("Use shared.", project_dictionary=project)


def test_sentence_and_paragraph_limits_use_block_context() -> None:
    long_procedure = "1. " + " ".join(f"word{index}" for index in range(21)) + "."
    long_description = " ".join(f"item{index}" for index in range(26)) + "."
    seven_sentences = " ".join(f"Sentence {index}." for index in range(7))
    text = f"{long_procedure}\n\n{long_description}\n\n{seven_sentences}"

    result = analyze(text)
    rule_ids = [finding.rule_id for finding in result.findings]
    assert "5.1" in rule_ids
    assert "6.3" in rule_ids
    assert "6.6" in rule_ids
    assert (
        next(item for item in result.coverage if item.rule_id == "5.1").status
        is CoverageStatus.FAILED
    )


def test_decimal_does_not_hide_descriptive_sentence_violation() -> None:
    text = " ".join(f"word{index}" for index in range(25)) + " 1.5 bar."
    result = analyze(text)
    assert any(item.rule_id == "6.3" for item in result.findings)


def test_safety_instruction_uses_procedure_sentence_limit() -> None:
    warning = "WARNING: " + " ".join(f"word{index}" for index in range(21)) + "."
    result = analyze(warning)
    finding = next(item for item in result.findings if item.rule_id == "5.1")
    assert "maximum 20" in finding.message
    assert (
        next(item for item in result.coverage if item.rule_id == "5.1").status
        is CoverageStatus.FAILED
    )


def test_sentence_length_defers_possible_rule_86_groups_to_review() -> None:
    text = "1. " + " ".join(f"word{index}" for index in range(20)) + " New York."
    result = analyze(text)
    finding = next(item for item in result.findings if item.rule_id == "5.1")
    assert finding.kind is FindingKind.HUMAN_REVIEW
    assert "Rule 8.6" in finding.message


def test_full_check_can_pass_but_partial_check_never_implies_a_pass() -> None:
    result = analyze("Install the unit.")
    semicolon = next(item for item in result.coverage if item.rule_id == "8.1")
    contraction = next(item for item in result.coverage if item.rule_id == "4.2")
    grouped_elements = next(item for item in result.coverage if item.rule_id == "8.6")

    assert semicolon.status is CoverageStatus.PASSED
    assert contraction.status is CoverageStatus.NOT_CHECKED
    assert grouped_elements.status is CoverageStatus.NOT_CHECKED


def test_detector_findings_are_probable_and_report_only() -> None:
    detector = StaticDetector(
        model_id="detector-test",
        predictions=(
            DetectorPrediction(
                rule_id="3.6",
                score=0.8,
                message="Possible passive voice.",
                byte_range=ByteRange(start=0, end=3),
            ),
        ),
    )
    result = analyze("The unit was removed.", detector=detector)
    finding = next(item for item in result.findings if item.rule_id == "3.6")
    coverage = next(item for item in result.coverage if item.rule_id == "3.6")

    assert finding.kind is FindingKind.PROBABLE_VIOLATION
    assert finding.model_id == "detector-test"
    assert finding.checker_id is None
    assert coverage.status is CoverageStatus.PROBABLE_VIOLATION


def test_detector_cannot_return_unknown_rule_or_out_of_range_span() -> None:
    unknown = StaticDetector(
        model_id="bad",
        predictions=(DetectorPrediction(rule_id="99.1", score=0.5, message="bad"),),
    )
    try:
        analyze("Text.", detector=unknown)
    except ValueError as error:
        assert "unknown rule" in str(error)
    else:
        raise AssertionError("unknown detector rule was accepted")

    outside = StaticDetector(
        model_id="bad",
        predictions=(
            DetectorPrediction(
                rule_id="3.6",
                score=0.5,
                message="bad",
                byte_range=ByteRange(start=0, end=100),
            ),
        ),
    )
    try:
        analyze("Text.", detector=outside)
    except ValueError as error:
        assert "outside" in str(error)
    else:
        raise AssertionError("out-of-range detector span was accepted")
