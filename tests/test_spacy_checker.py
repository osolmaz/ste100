from __future__ import annotations

import pytest

from ste100.checker import analyze
from ste100.linguistics import SpacyAnalyzer
from ste100.models import CoverageStatus, Finding, FindingKind
from ste100.standard import load_bundled_standard


@pytest.fixture(scope="module")
def analyzer() -> SpacyAnalyzer:
    return SpacyAnalyzer("en_core_web_sm")


def _rule_findings(text: str, rule_id: str, analyzer: SpacyAnalyzer) -> list[Finding]:
    return [
        finding
        for finding in analyze(text, linguistic_analyzer=analyzer).findings
        if finding.rule_id == rule_id
    ]


def test_spacy_pipeline_is_pinned_and_supplies_expected_analysis(
    analyzer: SpacyAnalyzer,
) -> None:
    assert analyzer.analyzer_id == "spacy:en_core_web_sm:3.8.0"
    sentence = analyzer.analyze("1. Open the access panel.")[0]
    open_token = next(token for token in sentence.tokens if token.text == "Open")
    assert (open_token.lemma, open_token.pos, open_token.tag, open_token.dependency) == (
        "open",
        "VERB",
        "VB",
        "ROOT",
    )


def test_manually_verified_imperative_passes(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("1. Open the access panel.", "5.3", analyzer) == []


def test_manually_verified_passive_instruction_fails(analyzer: SpacyAnalyzer) -> None:
    text = "1. The access panel is opened."
    imperative = _rule_findings(text, "5.3", analyzer)
    passive = _rule_findings(text, "3.6", analyzer)
    assert imperative[0].kind is FindingKind.VIOLATION
    assert {item.kind for item in passive} == {FindingKind.VIOLATION}


def test_descriptive_passive_abstains_for_agent_review(analyzer: SpacyAnalyzer) -> None:
    findings = _rule_findings("The panel was removed.", "3.6", analyzer)
    assert findings
    assert {item.kind for item in findings} == {FindingKind.HUMAN_REVIEW}


def test_note_instruction_is_rejected(analyzer: SpacyAnalyzer) -> None:
    finding = _rule_findings("NOTE: Open the valve.", "5.5", analyzer)[0]
    assert finding.kind is FindingKind.VIOLATION


def test_informational_note_is_not_rejected(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("NOTE: The valve stays open during the test.", "5.5", analyzer) == []


def test_multiple_procedure_actions_abstain_for_simultaneity_review(
    analyzer: SpacyAnalyzer,
) -> None:
    finding = _rule_findings("1. Open the panel and remove the filter.", "5.2", analyzer)[0]
    assert finding.kind is FindingKind.HUMAN_REVIEW


def test_safety_command_passes_and_descriptive_opening_abstains(
    analyzer: SpacyAnalyzer,
) -> None:
    assert _rule_findings("WARNING: Remove the fuse.", "7.2", analyzer) == []
    review = _rule_findings("WARNING: The fuse is hot.", "7.2", analyzer)[0]
    assert review.kind is FindingKind.HUMAN_REVIEW


def test_ing_form_abstains_for_technical_noun_review(analyzer: SpacyAnalyzer) -> None:
    finding = _rule_findings("The technician is removing the panel.", "3.5", analyzer)[0]
    assert finding.excerpt == "removing"
    assert finding.kind is FindingKind.HUMAN_REVIEW


def test_unlisted_verb_form_is_conclusive(analyzer: SpacyAnalyzer) -> None:
    findings = _rule_findings("The technician is removing the panel.", "3.1", analyzer)
    assert findings[0].excerpt == "removing"
    assert findings[0].kind is FindingKind.VIOLATION


def test_approved_verb_form_is_not_rejected(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("The technician removed the panel.", "3.1", analyzer) == []


def test_approved_word_in_unapproved_part_of_speech_fails(analyzer: SpacyAnalyzer) -> None:
    finding = _rule_findings("The use is clear.", "1.2", analyzer)[0]
    assert finding.excerpt == "use"
    assert finding.kind is FindingKind.VIOLATION


def test_omitted_that_requires_a_finite_subordinate_clause(
    analyzer: SpacyAnalyzer,
) -> None:
    review = _rule_findings("Make sure the valve is open.", "GR-1", analyzer)
    assert review and {item.kind for item in review} == {FindingKind.HUMAN_REVIEW}
    assert _rule_findings("Make sure that the valve is open.", "GR-1", analyzer) == []
    assert _rule_findings("Show the result.", "GR-1", analyzer) == []
    assert _rule_findings("Show how to remove the cover.", "GR-1", analyzer) == []


def test_spacy_rules_remain_human_review_when_analyzer_is_absent() -> None:
    result = analyze("1. Open the panel.")
    coverage = next(item for item in result.coverage if item.rule_id == "5.3")
    assert coverage.status is CoverageStatus.HUMAN_REVIEW


def test_manually_verified_standard_note_examples(analyzer: SpacyAnalyzer) -> None:
    examples = [
        example for example in load_bundled_standard().examples if "5.5" in example.rule_ids
    ]
    assert {example.label for example in examples} == {"positive", "negative"}
    for example in examples:
        failed = {
            finding.rule_id
            for finding in analyze(example.text, linguistic_analyzer=analyzer).findings
            if finding.kind is FindingKind.VIOLATION
        }
        assert ("5.5" in failed) is (example.label == "negative")


def test_missing_spacy_pipeline_has_clear_error() -> None:
    with pytest.raises(RuntimeError, match="pipeline is not installed"):
        SpacyAnalyzer("missing_ste100_test_pipeline")
