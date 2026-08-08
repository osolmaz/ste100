from __future__ import annotations

import json

import pytest

from ste100.checker import analyze
from ste100.models import ProjectDictionary, ProjectTerm
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


def _excerpts(text: str, rule_id: str) -> list[str]:
    return [finding.excerpt for finding in analyze(text).findings if rule_id in finding.rule_ids]


def test_result_is_binary_and_has_no_coverage_or_review_state() -> None:
    passed = analyze("Continue.")
    failed = analyze("Utilize.")
    assert passed.passed and passed.findings == ()
    assert not failed.passed and failed.findings
    encoded = json.dumps(failed.model_dump(mode="json"))
    assert "human_review" not in encoded
    assert "coverage" not in encoded
    assert "review_state" not in encoded


def test_bundled_dictionary_is_used_by_default() -> None:
    result = analyze("Utilize the component.")
    finding = next(item for item in result.findings if item.excerpt == "Utilize")
    assert finding.rule_ids == ("1.1", "1.6")
    assert "listed as unapproved" in finding.message
    assert "Review" not in finding.message
    assert result.standard_digest == load_bundled_standard().manifest.source.source_digest


def test_unapproved_word_emits_one_finding_with_both_rules() -> None:
    findings = [item for item in analyze("Use this option.").findings if item.excerpt == "option"]
    assert len(findings) == 1
    assert findings[0].rule_ids == ("1.1", "1.6")
    assert "alternative" in findings[0].message


def test_unknown_word_fails_without_speculation() -> None:
    finding = next(
        item
        for item in analyze("Install the xylophonium.").findings
        if item.excerpt == "xylophonium"
    )
    assert finding.rule_ids == ("1.1",)
    assert finding.message == (
        "'xylophonium' is not in the extracted STE dictionary or the supplied project dictionary."
    )


def test_vocabulary_respects_project_terms(standard_pack: StandardPack) -> None:
    result = analyze(
        "Utilize the fuel pump.",
        standard=standard_pack,
        project_dictionary=_project_dictionary(),
    )
    assert [(item.excerpt, item.rule_ids) for item in result.findings] == [
        ("Utilize", ("1.1", "1.6"))
    ]


def test_approved_multiword_entry_occupies_its_full_range() -> None:
    result = analyze("The test is in progress.")
    assert not [
        finding
        for finding in result.findings
        if finding.excerpt in {"in progress", "progress"} and {"1.1", "1.6"} & set(finding.rule_ids)
    ]


def test_approved_ellipsis_entry_matches_words_as_placeholders() -> None:
    result = analyze("The tube is as fast as the pump.")
    assert not [
        finding
        for finding in result.findings
        if finding.excerpt in {"as", "as fast as", "fast"}
        and {"1.1", "1.6"} & set(finding.rule_ids)
    ]


def test_ambiguous_dictionary_word_fails_once() -> None:
    findings = [item for item in analyze("Get the tool.").findings if item.excerpt == "Get"]
    assert len(findings) == 1
    assert findings[0].rule_ids == ("1.1", "1.6")
    assert "both approved and unapproved" in findings[0].message


def test_hyphenated_unapproved_headword_is_checked() -> None:
    finding = next(
        item for item in analyze("Air-dry the filter.").findings if item.excerpt == "Air-dry"
    )
    assert finding.rule_ids == ("1.1", "1.6")


def test_contractions_are_found_but_possessives_are_not() -> None:
    text = "Don't move it. It won\u2019t move. Let's stop. Where's the tool?"
    assert _excerpts(text, "4.2") == ["Don't", "won\u2019t", "Let's", "Where's"]
    assert _excerpts("The pump's cover is open.", "4.2") == []


@pytest.mark.parametrize(
    ("text", "rule_id", "excerpt"),
    [
        ("Use a semicolon; here.", "8.1", ";"),
        ("Use the colour indicator.", "1.14", "colour"),
    ],
)
def test_exact_word_and_punctuation_checks(text: str, rule_id: str, excerpt: str) -> None:
    assert excerpt in _excerpts(text, rule_id)


def test_general_recommendations_do_not_emit_findings() -> None:
    result = analyze("Use the tool, e.g. a wrench. The operator puts his tools here.")
    assert not [
        finding
        for finding in result.findings
        if any(rule_id.startswith("GR-") for rule_id in finding.rule_ids)
    ]


def test_protected_values_are_excluded_from_prose_checks() -> None:
    text = "https://example.test/colour COLOUR-123 `colour; don't` colour"
    result = analyze(text)
    assert _excerpts(text, "1.14") == ["colour"]
    assert not [
        item
        for item in result.findings
        if item.excerpt in {";", "don't"} and {"4.2", "8.1"} & set(item.rule_ids)
    ]


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
    result = analyze("Check the colour sensor.", project_dictionary=project)
    assert not [item for item in result.findings if "1.14" in item.rule_ids]


@pytest.mark.parametrize("text", ["Install the cover (item 2.", "Install item 2)."])
def test_unbalanced_parentheses(text: str) -> None:
    finding = next(item for item in analyze(text).findings if "8.3" in item.rule_ids)
    assert finding.excerpt in {"(", ")"}


def test_balanced_parentheses_do_not_fail_rule_8_3() -> None:
    assert _excerpts("Install the cover (item 2).", "8.3") == []


def test_unapproved_multiword_does_not_create_phrasal_verb_claim() -> None:
    result = analyze("Carry out the test.")
    finding = next(item for item in result.findings if item.excerpt == "Carry out")
    assert finding.rule_ids == ("1.1", "1.6")
    assert all("9.3" not in item.rule_ids for item in result.findings)


def test_vertical_list_requires_a_colon() -> None:
    bad = "Use these items.\n1. A wrench.\n2. A cloth."
    good = "Use these items:\n1. A wrench.\n2. A cloth."
    assert _excerpts(bad, "4.3")
    assert _excerpts(good, "4.3") == []


def test_protected_code_is_excluded_from_structure_checks() -> None:
    code = " ".join(f"token{index}" for index in range(30))
    result = analyze(f"```text\n{code}\nUse these items.\n1. A wrench.\n```")
    assert not [
        item for item in result.findings if {"4.3", "5.1", "6.3", "6.6"} & set(item.rule_ids)
    ]


def test_unsupported_condition_comma_guess_emits_nothing() -> None:
    assert _excerpts("1. If the panel is hot.", "5.4") == []
    assert _excerpts("1. If the light comes on stop the test.", "5.4") == []


def test_procedure_and_descriptive_sentence_limits() -> None:
    procedure = "1. " + " ".join(f"word{index}" for index in range(21)) + "."
    descriptive = " ".join(f"word{index}" for index in range(26)) + "."
    assert _excerpts(procedure, "5.1")
    assert _excerpts(descriptive, "6.3")


def test_exact_length_boundaries_pass() -> None:
    procedure = "1. " + " ".join(f"word{index}" for index in range(20)) + "."
    descriptive = " ".join(f"word{index}" for index in range(25)) + "."
    assert _excerpts(procedure, "5.1") == []
    assert _excerpts(descriptive, "6.3") == []


def test_protected_numbers_still_count_as_words() -> None:
    text = " ".join(str(index) for index in range(1, 27)) + "."
    finding = next(item for item in analyze(text).findings if "6.3" in item.rule_ids)
    assert "26 words" in finding.message


def test_grouped_elements_do_not_produce_an_uncertain_length_finding() -> None:
    text = "1. " + " ".join(["New York"] * 11) + "."
    assert _excerpts(text, "5.1") == []


def test_note_uses_descriptive_limit() -> None:
    note = "NOTE: " + " ".join(f"word{index}" for index in range(26)) + "."
    finding = next(item for item in analyze(note).findings if "6.3" in item.rule_ids)
    assert "26 words" in finding.message


def test_paragraph_sentence_limit() -> None:
    result = analyze("One. Two. Three. Four. Five. Six. Seven.")
    assert any("6.6" in item.rule_ids for item in result.findings)


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
    finding = next(item for item in analyze("Café; stop.").findings if "8.1" in item.rule_ids)
    assert (finding.byte_range.start, finding.byte_range.end) == (5, 6)
    assert finding.excerpt == ";"
