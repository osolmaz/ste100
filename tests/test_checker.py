from __future__ import annotations

import pytest

from ste100.checker import analyze
from ste100.models import CoverageStatus, FindingKind, ProjectDictionary, ProjectTerm
from ste100.standard import StandardPack, load_bundled_standard


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


def _findings(text: str, rule_id: str) -> list[tuple[FindingKind, str | None]]:
    return [
        (finding.kind, finding.excerpt)
        for finding in analyze(text).findings
        if finding.rule_id == rule_id
    ]


def test_bundled_dictionary_is_used_by_default() -> None:
    result = analyze("Utilize the component.")
    finding = next(
        item for item in result.findings if item.rule_id == "1.1" and item.excerpt == "Utilize"
    )
    assert finding.kind is FindingKind.HUMAN_REVIEW
    assert len(result.coverage) == 61
    assert result.standard_digest == load_bundled_standard().manifest.source.source_digest


def test_vocabulary_respects_project_terms(standard_pack: StandardPack) -> None:
    result = analyze(
        "Utilize the fuel pump.",
        standard=standard_pack,
        project_dictionary=_project_dictionary(),
    )
    vocabulary = [item for item in result.findings if item.rule_id == "1.1"]
    assert [(item.kind, item.excerpt) for item in vocabulary] == [
        (FindingKind.HUMAN_REVIEW, "Utilize")
    ]
    assert "Use: use." in vocabulary[0].message


def test_unknown_vocabulary_requests_human_review() -> None:
    result = analyze("Install the xylophonium.")
    finding = next(item for item in result.findings if item.excerpt == "xylophonium")
    coverage = next(item for item in result.coverage if item.rule_id == "1.1")
    assert finding.kind is FindingKind.HUMAN_REVIEW
    assert coverage.status is CoverageStatus.HUMAN_REVIEW


def test_unapproved_noun_can_be_project_terminology() -> None:
    finding = next(
        item
        for item in analyze("Check the backup pump.").findings
        if item.rule_id == "1.1" and item.excerpt == "backup"
    )
    assert finding.kind is FindingKind.HUMAN_REVIEW


def test_hyphenated_dictionary_headword_is_checked() -> None:
    finding = next(
        item
        for item in analyze("Air-dry the filter.").findings
        if item.rule_id == "1.1" and item.excerpt == "Air-dry"
    )
    assert finding.kind is FindingKind.HUMAN_REVIEW
    assert "listed as unapproved" in finding.message


def test_word_with_approved_and_unapproved_uses_requests_review() -> None:
    result = analyze("Get the tool.")
    finding = next(item for item in result.findings if item.excerpt == "Get")
    assert finding.kind is FindingKind.HUMAN_REVIEW
    assert "part of speech and meaning" in finding.message


def test_contractions_are_found_but_possessives_are_not() -> None:
    text = "Don't move it. It won\u2019t move. Let's stop. Where's the tool?"
    assert [excerpt for _, excerpt in _findings(text, "4.2")] == [
        "Don't",
        "won\u2019t",
        "Let's",
        "Where's",
    ]
    assert _findings("The pump's cover is open.", "4.2") == []


@pytest.mark.parametrize(
    ("text", "excerpt"),
    [
        ("Use a semicolon; here.", ";"),
        ("Use the colour indicator.", "colour"),
        ("Use the tool, e.g. a wrench.", "e.g."),
        ("The operator puts his tools here.", "his"),
    ],
)
def test_mechanical_word_and_punctuation_checks(text: str, excerpt: str) -> None:
    assert any(item.excerpt == excerpt for item in analyze(text).findings)


def test_american_spelling_message_gives_replacement() -> None:
    finding = next(item for item in analyze("Check the tyre.").findings if item.rule_id == "1.14")
    assert finding.excerpt == "tyre"
    assert "tire" in finding.message


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("Use a tool, e.g. a wrench.", "GR-6"),
        ("The operator puts his tools here.", "GR-7"),
    ],
)
def test_general_recommendations_never_create_violations(text: str, rule_id: str) -> None:
    findings = [item for item in analyze(text).findings if item.rule_id == rule_id]
    assert findings
    assert {item.kind for item in findings} == {FindingKind.HUMAN_REVIEW}


def test_protected_values_are_excluded_from_prose_checks() -> None:
    text = "https://example.test/colour COLOUR-123 `colour; don't` colour"
    result = analyze(text)
    spelling = [item for item in result.findings if item.rule_id == "1.14"]
    assert [(item.excerpt, item.kind) for item in spelling] == [("colour", FindingKind.VIOLATION)]
    assert not [item for item in result.findings if item.rule_id in {"4.2", "8.1"}]


def test_project_terms_are_excluded_from_spelling_checks() -> None:
    project = ProjectDictionary(
        format_version="1",
        terms=(
            ProjectTerm(
                term="colour sensor",
                category="technical_noun",
                meaning="A project-defined sensor",
                source="project glossary",
            ),
        ),
    )
    assert not [
        item
        for item in analyze("Check the colour sensor.", project_dictionary=project).findings
        if item.rule_id == "1.14"
    ]


@pytest.mark.parametrize("text", ["Install the cover (item 2.", "Install item 2)."])
def test_unbalanced_parentheses(text: str) -> None:
    finding = next(item for item in analyze(text).findings if item.rule_id == "8.3")
    assert finding.kind is FindingKind.VIOLATION
    assert finding.excerpt in {"(", ")"}


def test_balanced_parentheses_do_not_fail_rule_8_3() -> None:
    assert _findings("Install the cover (item 2).", "8.3") == []


def test_unapproved_phrasal_verb_has_two_rule_findings() -> None:
    result = analyze("Carry out the test.")
    pairs = {(item.rule_id, item.excerpt) for item in result.findings}
    assert ("1.1", "Carry out") in pairs
    assert ("9.3", "Carry out") in pairs


def test_vertical_list_requires_a_colon() -> None:
    bad = "Use these items.\n1. A wrench.\n2. A cloth."
    good = "Use these items:\n1. A wrench.\n2. A cloth."
    assert _findings(bad, "4.3")
    assert _findings(good, "4.3") == []


def test_long_protected_code_is_excluded_from_sentence_limits() -> None:
    code = " ".join(f"token{index}" for index in range(30))
    result = analyze(f"```text\n{code}\n```")
    assert not [item for item in result.findings if item.rule_id in {"5.1", "6.3", "6.6"}]


def test_vertical_lists_in_protected_code_are_ignored() -> None:
    text = "```text\nUse these items.\n1. A wrench.\n```"
    assert _findings(text, "4.3") == []


def test_colon_led_vertical_list_is_applicable_to_word_count() -> None:
    result = analyze("Use these items:\n1. A wrench.\n2. A cloth.")
    coverage = next(item for item in result.coverage if item.rule_id == "8.4")
    assert coverage.status is CoverageStatus.PASSED


def test_initial_procedure_condition_without_comma_requests_review() -> None:
    bad = "1. If the light comes on stop the test."
    good = "1. If the light comes on, stop the test."
    assert _findings(bad, "5.4") == [(FindingKind.HUMAN_REVIEW, bad)]
    assert _findings(good, "5.4") == []


def test_condition_without_a_command_does_not_fail() -> None:
    result = analyze("1. If the panel is hot.")
    assert not [
        item
        for item in result.findings
        if item.rule_id == "5.4" and item.kind is FindingKind.VIOLATION
    ]


def test_procedure_and_descriptive_sentence_limits() -> None:
    procedure = "1. " + " ".join(f"word{index}" for index in range(21)) + "."
    descriptive = " ".join(f"word{index}" for index in range(26)) + "."
    assert _findings(procedure, "5.1")
    assert _findings(descriptive, "6.3")


def test_exact_length_boundaries_pass() -> None:
    procedure = "1. " + " ".join(f"word{index}" for index in range(20)) + "."
    descriptive = " ".join(f"word{index}" for index in range(25)) + "."
    assert _findings(procedure, "5.1") == []
    assert _findings(descriptive, "6.3") == []


def test_note_uses_descriptive_limit() -> None:
    note = "NOTE: " + " ".join(f"word{index}" for index in range(26)) + "."
    finding = next(item for item in analyze(note).findings if item.rule_id == "6.3")
    assert "mechanical count of 26" in finding.message


def test_paragraph_sentence_limit() -> None:
    result = analyze("One. Two. Three. Four. Five. Six. Seven.")
    finding = next(item for item in result.findings if item.rule_id == "6.6")
    assert finding.kind is FindingKind.VIOLATION


def test_grouped_element_length_is_review_not_failure() -> None:
    text = "1. " + " ".join(["New York"] * 11) + "."
    finding = next(item for item in analyze(text).findings if item.rule_id == "5.1")
    assert finding.kind is FindingKind.HUMAN_REVIEW
    assert "Rule 8.6" in finding.message


def test_coverage_uses_only_four_public_statuses() -> None:
    result = analyze("Install the unit.")
    assert {item.status.value for item in result.coverage} <= {
        "passed",
        "failed",
        "human_review",
        "not_applicable",
    }
    semicolon = next(item for item in result.coverage if item.rule_id == "8.1")
    contextual = next(item for item in result.coverage if item.rule_id == "6.5")
    assert semicolon.status is CoverageStatus.PASSED
    assert contextual.status is CoverageStatus.HUMAN_REVIEW


def test_analyze_rejects_invalid_project_dictionary() -> None:
    project = ProjectDictionary(
        format_version="1",
        terms=(
            ProjectTerm(
                term="hydraulic pressure control valve",
                category="technical_noun",
                meaning="A valve",
                source="project glossary",
            ),
        ),
    )
    with pytest.raises(ValueError, match="more than three words"):
        analyze("Text.", project_dictionary=project)


def test_findings_keep_utf8_byte_offsets() -> None:
    finding = next(item for item in analyze("Café; stop.").findings if item.rule_id == "8.1")
    assert finding.byte_range is not None
    assert (finding.byte_range.start, finding.byte_range.end) == (5, 6)
    assert finding.excerpt == ";"
