from __future__ import annotations

import pytest

from ste100.document import BlockKind, parse_document, sentence_ranges, slice_bytes, tokenize
from ste100.models import ByteRange


def test_parser_preserves_utf8_byte_offsets_and_blocks() -> None:
    text = "NOTE: Café data is available.\n\n1. Install the unit.\n\n- First item: Second item."
    document = parse_document(text)

    assert [block.kind for block in document.blocks] == [
        BlockKind.NOTE,
        BlockKind.PROCEDURE,
        BlockKind.LIST,
    ]
    assert slice_bytes(text, document.blocks[0].byte_range) == "NOTE: Café data is available."
    assert [sentence.text for sentence in document.blocks[2].sentences] == [
        "- First item:",
        "Second item.",
    ]


def test_sentence_splitter_does_not_split_common_abbreviations() -> None:
    text = "Use approved units, e.g. N and mm. Then continue."
    ranges = sentence_ranges(text)
    assert [text[start:end] for start, end in ranges] == [
        "Use approved units, e.g. N and mm.",
        "Then continue.",
    ]


def test_decimal_point_is_not_a_sentence_boundary() -> None:
    text = "Set the pressure to 1.5 bar. Then continue."
    ranges = sentence_ranges(text)
    assert [text[start:end] for start, end in ranges] == [
        "Set the pressure to 1.5 bar.",
        "Then continue.",
    ]


def test_word_count_exceptions_are_single_tokens() -> None:
    text = 'Move the pre-load unit (item 4) by 10 mm to "ZONE A" at https://example.com.'
    tokens = tokenize(text)
    values = [token.text for token in tokens]
    assert "pre-load" in values
    assert "(item 4)" in values
    assert "10 mm" in values
    assert '"ZONE A"' in values
    assert "https://example.com." in values


def test_colon_terminates_intro_before_vertical_list() -> None:
    text = "Use these items:\n- First item.\n- Second item."
    document = parse_document(text)
    assert [sentence.text for sentence in document.sentences] == [
        "Use these items:",
        "- First item.",
        "- Second item.",
    ]


def test_parenthetical_prose_is_also_a_separate_sentence() -> None:
    text = "Make sure that the switch is released (the EMER legend is off)."
    document = parse_document(text)
    assert [sentence.text for sentence in document.sentences] == [
        text,
        "the EMER legend is off",
    ]
    assert document.sentences[0].word_count == 8
    assert document.sentences[1].word_count == 5


def test_procedure_marker_is_not_a_counted_word() -> None:
    text = "1. " + " ".join(f"word{index}" for index in range(20)) + "."
    sentence = parse_document(text).sentences[0]
    assert sentence.word_count == 20
    assert sentence.tokens[0].text == "word0"


def test_slice_bytes_rejects_mid_character_boundary() -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        slice_bytes("é", ByteRange(start=1, end=2))


def test_empty_document_has_no_blocks() -> None:
    assert parse_document("").blocks == ()
    assert parse_document("\n\n").blocks == ()
