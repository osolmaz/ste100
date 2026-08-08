from __future__ import annotations

import pytest

import ste100.protection as protection_module
from ste100.models import ByteRange, ProjectDictionary, ProjectTerm
from ste100.protection import ProtectedContentError, protect_text
from ste100.standard import StandardPack
from ste100.terminology import TermMatcher, validate_project_dictionary


def _project() -> ProjectDictionary:
    return ProjectDictionary(
        format_version="1",
        terms=(
            ProjectTerm(
                term="pump",
                category="technical_noun",
                meaning="A generic pump",
                source="glossary",
            ),
            ProjectTerm(
                term="fuel pump",
                category="technical_noun",
                approved_forms=("fuel pumps",),
                meaning="A pump for fuel",
                source="glossary",
            ),
        ),
    )


def test_longest_project_term_match_wins() -> None:
    matches = TermMatcher(_project()).find("The fuel pump supplies the pump.")
    assert [item.text for item in matches] == ["fuel pump", "pump"]
    assert [item.term.term for item in matches] == ["fuel pump", "pump"]


def test_project_dictionary_rejects_long_and_ambiguous_terms() -> None:
    project = ProjectDictionary(
        format_version="1",
        terms=(
            ProjectTerm(
                term="very long technical noun",
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
    report = validate_project_dictionary(project)
    assert {issue.code for issue in report.issues} == {
        "long_technical_noun",
        "ambiguous_project_term",
    }


def test_project_dictionary_checks_every_form_against_standard(
    standard_pack: StandardPack,
) -> None:
    project = ProjectDictionary(
        format_version="1",
        terms=(
            ProjectTerm(
                term="fuel pump",
                category="technical_noun",
                approved_forms=("utilize",),
                meaning="A pump for fuel",
                source="glossary",
            ),
        ),
    )
    report = validate_project_dictionary(project, standard=standard_pack)
    assert not report.valid
    assert [(issue.code, issue.message) for issue in report.issues] == [
        ("standard_conflict", "project term form is unapproved in the standard: utilize")
    ]


def test_protection_round_trip_preserves_all_facts() -> None:
    text = "Set FUEL_VALVE to 10 mm on the fuel pump; see https://example.com/x and `x += 1`."
    protected = protect_text(text, project_dictionary=_project())

    assert {span.kind for span in protected.spans} == {
        "identifier",
        "unit",
        "project_term",
        "url",
        "code",
    }
    candidate = protected.masked_text.replace("Set", "Adjust").replace("; see", ". Refer to")
    restored = protected.restore(candidate)
    assert "FUEL_VALVE" in restored
    assert "10 mm" in restored
    assert "fuel pump" in restored
    assert "https://example.com/x" in restored
    assert "`x += 1`" in restored


@pytest.mark.parametrize("identifier", ["L42", "A320", "36L7"])
def test_part_number_shapes_are_protected(identifier: str) -> None:
    text = f"Install {identifier} now."
    protected = protect_text(text)
    assert identifier in protected.originals
    assert any(span.kind == "identifier" for span in protected.spans)


def test_protection_rejects_drop_duplicate_reorder_and_unknown() -> None:
    protected = protect_text("Move ID_A by 10 mm.")
    first, second = protected.sentinels
    cases = [
        protected.masked_text.replace(first, ""),
        protected.masked_text.replace(first, first + first),
        protected.masked_text.replace(first, "TEMP").replace(second, first).replace("TEMP", second),
        protected.masked_text + f" {protected.sentinel_prefix}9999__",
        protected.masked_text + f" {protected.sentinel_prefix}10000__",
    ]
    for candidate in cases:
        with pytest.raises(ProtectedContentError):
            protected.restore(candidate)


def test_overlapping_caller_ranges_are_rejected() -> None:
    with pytest.raises(ProtectedContentError, match="overlap"):
        protect_text(
            "abcdef",
            caller_ranges=(ByteRange(start=0, end=4), ByteRange(start=2, end=6)),
        )


def test_protected_span_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(protection_module, "_MAX_PROTECTED_SPANS", 1)
    with pytest.raises(ProtectedContentError, match="exceed"):
        protect_text("Install ID_A at 10 mm.")


def test_literal_sentinel_shaped_source_text_round_trips() -> None:
    text = "Keep __STE100_0000__ and __STE100_deadbeef0000_0000__ literal."
    protected = protect_text(text)
    assert protected.restore(protected.masked_text) == text
    assert protected.sentinel_prefix not in text


def test_caller_range_must_align_with_utf8_and_is_restored() -> None:
    text = "Keep café unchanged."
    start = len(b"Keep ")
    end = start + len("café".encode())
    protected = protect_text(text, caller_ranges=(ByteRange(start=start, end=end),))
    assert protected.spans[0].kind == "caller"
    assert protected.restore(protected.masked_text) == text

    with pytest.raises(ProtectedContentError, match="UTF-8"):
        protect_text(text, caller_ranges=(ByteRange(start=start + 4, end=end),))
