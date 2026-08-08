from __future__ import annotations

from types import SimpleNamespace

import pytest
import spacy

from ste100.checker import analyze
from ste100.linguistics import SpacyAnalyzer
from ste100.models import Finding, ProjectDictionary, ProjectTerm


@pytest.fixture(scope="module")
def analyzer() -> SpacyAnalyzer:
    return SpacyAnalyzer()


def _rule_findings(text: str, rule_id: str, analyzer: SpacyAnalyzer) -> list[Finding]:
    return [
        finding
        for finding in analyze(text, linguistic_analyzer=analyzer).findings
        if rule_id in finding.rule_ids
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


def test_manually_verified_imperatives_pass(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("1. Open the access panel.", "5.3", analyzer) == []
    assert _rule_findings("1. Do not touch the valve.", "5.3", analyzer) == []
    assert _rule_findings("1. Make sure that the valve is open.", "5.3", analyzer) == []


def test_note_instruction_is_rejected(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("NOTE: Open the valve.", "5.5", analyzer)
    assert _rule_findings("NOTE: Do not touch the valve.", "5.5", analyzer)
    assert _rule_findings("NOTE: The valve stays open during the test.", "5.5", analyzer) == []


def test_passive_instruction_fails_once(analyzer: SpacyAnalyzer) -> None:
    text = "1. The access panel is opened."
    assert _rule_findings(text, "5.3", analyzer)
    passive = _rule_findings(text, "3.6", analyzer)
    assert len(passive) == 1


def test_descriptive_passive_emits_no_unsupported_finding(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("The panel was removed.", "3.6", analyzer) == []


def test_multiple_actions_emit_no_unsupported_finding(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("1. Open the panel and remove the filter.", "5.2", analyzer) == []


def test_safety_opening_uses_verified_command_or_condition(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("WARNING: Remove the fuse.", "7.2", analyzer) == []
    assert _rule_findings("WARNING: If the fuse is hot, do not touch it.", "7.2", analyzer) == []
    assert _rule_findings("WARNING: The fuse is hot.", "7.2", analyzer)


def test_ambiguous_ing_and_complex_verb_checks_emit_nothing(
    analyzer: SpacyAnalyzer,
) -> None:
    text = "The technician is removing the panel."
    assert _rule_findings(text, "3.2", analyzer) == []
    assert _rule_findings(text, "3.4", analyzer) == []
    assert _rule_findings(text, "3.5", analyzer) == []


def test_unlisted_verb_form_is_reported(analyzer: SpacyAnalyzer) -> None:
    findings = _rule_findings("The technician is removing the panel.", "3.1", analyzer)
    assert findings[0].excerpt == "removing"


def test_spacy_selects_approved_use_of_mixed_status_word(
    analyzer: SpacyAnalyzer,
) -> None:
    assert any(item.excerpt == "back" for item in analyze("Move back.").findings)
    result = analyze("Move back.", linguistic_analyzer=analyzer)
    assert not [item for item in result.findings if item.excerpt == "back"]


def test_approved_forms_are_not_rejected(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("The technician removed the panel.", "3.1", analyzer) == []
    assert _rule_findings("The hole is deeper.", "1.4", analyzer) == []


def test_unapproved_nontechnical_part_of_speech_is_one_finding(
    analyzer: SpacyAnalyzer,
) -> None:
    findings = [
        finding
        for finding in analyze("The movement is abrupt.", linguistic_analyzer=analyzer).findings
        if finding.excerpt == "abrupt"
    ]
    assert len(findings) == 1
    assert findings[0].rule_ids == ("1.1", "1.6")


def test_approved_word_in_unapproved_part_of_speech_fails(analyzer: SpacyAnalyzer) -> None:
    finding = _rule_findings("The use is clear.", "1.2", analyzer)[0]
    assert finding.excerpt == "use"


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
        if finding.excerpt == "use" and {"1.1", "1.2", "1.4"} & set(finding.rule_ids)
    ]
    verb_result = analyze("Use the tool.", project_dictionary=project, linguistic_analyzer=analyzer)
    assert any("1.7" in finding.rule_ids for finding in verb_result.findings)
    code_result = analyze("`Use`", project_dictionary=project, linguistic_analyzer=analyzer)
    assert not [finding for finding in code_result.findings if "1.7" in finding.rule_ids]


def test_general_recommendation_does_not_emit_a_finding(analyzer: SpacyAnalyzer) -> None:
    assert _rule_findings("Make sure the valve is open.", "GR-1", analyzer) == []


def test_spacy_checks_ignore_inline_and_fenced_code(analyzer: SpacyAnalyzer) -> None:
    text = "Use `removing` as a code value.\n```text\nremoving removed\n```"
    result = analyze(text, linguistic_analyzer=analyzer)
    assert not [
        finding
        for finding in result.findings
        if finding.excerpt in {"removing", "removed"}
        and {"3.1", "3.2", "3.5", "3.6"} & set(finding.rule_ids)
    ]
    protected_root = analyze("1. `Open` the valve.", linguistic_analyzer=analyzer)
    assert not [finding for finding in protected_root.findings if "5.3" in finding.rule_ids]


def test_spacy_checks_are_absent_when_analyzer_is_absent() -> None:
    result = analyze("1. The panel is opened.")
    assert not [
        finding
        for finding in result.findings
        if {"1.2", "1.4", "3.1", "3.6", "5.3"} & set(finding.rule_ids)
    ]


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
    monkeypatch.setattr(spacy, "load", lambda _: SimpleNamespace(pipe_names=components, meta={}))
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
