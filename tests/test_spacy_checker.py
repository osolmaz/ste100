from __future__ import annotations

from types import SimpleNamespace

import pytest
import spacy

from ste100.checker import analyze
from ste100.linguistics import SpacyAnalyzer
from ste100.models import (
    CoverageStatus,
    Finding,
    FindingKind,
    ProjectDictionary,
    ProjectTerm,
)
from ste100.standard import load_bundled_standard


@pytest.fixture(scope="module")
def analyzer() -> SpacyAnalyzer:
    return SpacyAnalyzer()


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


def test_negative_imperatives_are_recognized(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("1. Do not touch the valve.", "5.3", analyzer) == []
    note = _rule_findings("NOTE: Do not touch the valve.", "5.5", analyzer)
    assert note and {finding.kind for finding in note} == {FindingKind.VIOLATION}
    assert _rule_findings("WARNING: Do not touch the valve.", "7.2", analyzer) == []


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


def test_approved_comparative_form_is_not_rejected(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("The hole is deeper.", "1.4", analyzer) == []


def test_unapproved_nontechnical_part_of_speech_is_conclusive(
    analyzer: SpacyAnalyzer,
) -> None:
    findings = _rule_findings("The movement is abrupt.", "1.1", analyzer)
    assert any(
        finding.excerpt == "abrupt" and finding.kind is FindingKind.VIOLATION
        for finding in findings
    )


def test_approved_word_in_unapproved_part_of_speech_fails(analyzer: SpacyAnalyzer) -> None:
    finding = _rule_findings("The use is clear.", "1.2", analyzer)[0]
    assert finding.excerpt == "use"
    assert finding.kind is FindingKind.VIOLATION


def test_project_term_exempts_generic_pos_checks_but_retains_category_check(
    analyzer: SpacyAnalyzer,
) -> None:
    project = ProjectDictionary(
        format_version="1",
        terms=(
            ProjectTerm(
                term="use",
                category="technical_noun",
                meaning="The intended function of a component",
                source="project glossary",
            ),
        ),
    )
    noun_result = analyze(
        "The use is clear.", project_dictionary=project, linguistic_analyzer=analyzer
    )
    assert not [
        finding
        for finding in noun_result.findings
        if finding.excerpt == "use" and finding.rule_id in {"1.1", "1.2", "1.4"}
    ]
    verb_result = analyze("Use the tool.", project_dictionary=project, linguistic_analyzer=analyzer)
    misuse = next(finding for finding in verb_result.findings if finding.rule_id == "1.7")
    assert misuse.kind is FindingKind.VIOLATION


def test_omitted_that_requires_a_finite_subordinate_clause(
    analyzer: SpacyAnalyzer,
) -> None:
    review = _rule_findings("Make sure the valve is open.", "GR-1", analyzer)
    assert review and {item.kind for item in review} == {FindingKind.HUMAN_REVIEW}
    assert _rule_findings("Make sure that the valve is open.", "GR-1", analyzer) == []
    assert _rule_findings("Show the result.", "GR-1", analyzer) == []
    assert _rule_findings("Show how to remove the cover.", "GR-1", analyzer) == []


def test_spacy_checks_ignore_inline_and_fenced_code(analyzer: SpacyAnalyzer) -> None:
    text = "Use `removing` as a code value.\n```text\nremoving removed\n```"
    result = analyze(text, linguistic_analyzer=analyzer)
    assert not [
        finding
        for finding in result.findings
        if finding.excerpt in {"removing", "removed"}
        and finding.rule_id in {"3.1", "3.2", "3.5", "3.6"}
    ]


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


@pytest.mark.parametrize(
    "components",
    [
        ("tagger", "sentencizer"),
        ("parser",),
        ("morphologizer", "sentencizer"),
    ],
)
def test_spacy_pipeline_requires_parser_and_pos_component(
    components: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        spacy,
        "load",
        lambda _: SimpleNamespace(pipe_names=components, meta={}),
    )
    with pytest.raises(RuntimeError, match="parser and a POS-producing component"):
        SpacyAnalyzer()


def test_spacy_pipeline_version_is_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        spacy,
        "load",
        lambda _: SimpleNamespace(pipe_names=("parser", "tagger"), meta={"version": "3.7.0"}),
    )
    with pytest.raises(RuntimeError, match=r"version must be 3\.8\.0"):
        SpacyAnalyzer()


def test_missing_spacy_pipeline_has_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_: str) -> None:
        raise OSError("missing")

    monkeypatch.setattr(spacy, "load", missing)
    with pytest.raises(RuntimeError, match="pipeline is not installed"):
        SpacyAnalyzer()
