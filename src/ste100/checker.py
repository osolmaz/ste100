"""Deterministic checks that emit source-backed ASD-STE100 issues."""

from __future__ import annotations

import re

from ste100.document import (
    Block,
    BlockKind,
    Document,
    char_to_byte_offsets,
    parse_document,
    slice_bytes,
)
from ste100.linguistics import LinguisticAnalyzer, LinguisticSentence, LinguisticToken
from ste100.models import AnalysisResult, ByteRange, DictionaryEntry, Finding, ProjectDictionary
from ste100.standard import StandardPack, load_bundled_standard
from ste100.terminology import TermMatch, TermMatcher, validate_project_dictionary

_APOSTROPHE = "['\u2019]"
_CONTRACTION_RE = re.compile(
    rf"\b(?:[A-Za-z]+n{_APOSTROPHE}t|[Ii]{_APOSTROPHE}m|"
    rf"[A-Za-z]+{_APOSTROPHE}(?:re|ve|ll|d)|"
    rf"(?:he|she|it|that|there|what|where|when|who|how|here|why|let){_APOSTROPHE}s)\b",
    re.IGNORECASE,
)
_LEXICAL_RE = re.compile(r"^[A-Za-z]+(?:'[A-Za-z]+)?(?:-[A-Za-z]+)*$")
_GROUPED_ELEMENT_RE = re.compile(
    r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){1,}\b"
)
_AMERICAN_SPELLINGS = {
    "aeroplane": "airplane",
    "aluminium": "aluminum",
    "analogue": "analog",
    "behaviour": "behavior",
    "centre": "center",
    "colour": "color",
    "defence": "defense",
    "fibre": "fiber",
    "fuelled": "fueled",
    "grey": "gray",
    "labour": "labor",
    "litre": "liter",
    "metre": "meter",
    "mould": "mold",
    "organisation": "organization",
    "programme": "program",
    "recognise": "recognize",
    "theatre": "theater",
    "tyre": "tire",
}
_CODE_RE = re.compile(r"```[\s\S]*?```|`[^`\n]+`")
_PROTECTED_VALUE_RE = re.compile(
    r"https?://[^\s<>()]+"
    r"|```[\s\S]*?```"
    r"|`[^`\n]+`"
    r"|\b[A-Z][A-Z0-9]*(?:[-_/][A-Z0-9]+)+\b"
    r"|\b[A-Za-z][A-Za-z0-9]*(?:[_/][A-Za-z0-9_-]+)+\b"
    r"|\b\d+(?:[.,]\d+)?(?:\s*(?:°?[A-Za-z%]+(?:[/-][A-Za-z%]+)*))?\b"
)
_VERTICAL_LIST_PRESENT_RE = re.compile(
    r":\s*\r?\n\s*(?:[-*•]|[a-z][.)]|\d+(?:\.\d+)*[.)])\s+",
    re.IGNORECASE,
)
_LIST_WITHOUT_COLON_RE = re.compile(
    r"(?m)^(?!\s*(?:[-*•]|[a-z][.)]|\d+(?:\.\d+)*[.)])\s)"
    r"(?P<intro>[^\n:]+[.!?])\s*\n\s*(?:[-*•]|[a-z][.)]|\d+(?:\.\d+)*[.)])\s+",
    re.IGNORECASE,
)
_SPACY_POS = {
    "NOUN": "noun",
    "PROPN": "noun",
    "VERB": "verb",
    "AUX": "verb",
    "ADJ": "adjective",
    "ADV": "adverb",
    "ADP": "preposition",
    "PRON": "pronoun",
    "DET": "article",
    "CCONJ": "conjunction",
    "SCONJ": "conjunction",
}


def _finding_for_rules(
    text: str,
    *,
    rule_ids: tuple[str, ...],
    message: str,
    byte_range: ByteRange,
) -> Finding:
    return Finding(
        rule_ids=rule_ids,
        message=message,
        byte_range=byte_range,
        excerpt=slice_bytes(text, byte_range),
    )


def _finding(
    text: str,
    *,
    rule_id: str,
    message: str,
    byte_range: ByteRange,
) -> Finding:
    return _finding_for_rules(
        text,
        rule_ids=(rule_id,),
        message=message,
        byte_range=byte_range,
    )


def _regex_findings(
    text: str,
    pattern: re.Pattern[str],
    *,
    rule_id: str,
    message: str,
    excluded: tuple[ByteRange, ...] = (),
) -> list[Finding]:
    offsets = char_to_byte_offsets(text)
    findings: list[Finding] = []
    for match in pattern.finditer(text):
        byte_range = ByteRange(start=offsets[match.start()], end=offsets[match.end()])
        if _overlaps(byte_range, excluded):
            continue
        findings.append(
            _finding(
                text,
                rule_id=rule_id,
                message=message,
                byte_range=byte_range,
            )
        )
    return findings


def _pattern_ranges(text: str, pattern: re.Pattern[str]) -> tuple[ByteRange, ...]:
    offsets = char_to_byte_offsets(text)
    return tuple(
        ByteRange(start=offsets[match.start()], end=offsets[match.end()])
        for match in pattern.finditer(text)
    )


def _protected_ranges(text: str, project: ProjectDictionary | None) -> tuple[ByteRange, ...]:
    ranges = list(_pattern_ranges(text, _PROTECTED_VALUE_RE))
    ranges.extend(match.byte_range for match in _project_matches(text, project))
    return tuple(ranges)


def _spelling_findings(text: str, excluded: tuple[ByteRange, ...]) -> list[Finding]:
    pattern = re.compile(
        rf"\b(?:{'|'.join(re.escape(word) for word in _AMERICAN_SPELLINGS)})\b", re.IGNORECASE
    )
    offsets = char_to_byte_offsets(text)
    findings: list[Finding] = []
    for match in pattern.finditer(text):
        byte_range = ByteRange(start=offsets[match.start()], end=offsets[match.end()])
        if _overlaps(byte_range, excluded):
            continue
        replacement = _AMERICAN_SPELLINGS[match.group().casefold()]
        findings.append(
            _finding(
                text,
                rule_id="1.14",
                message=f"Use American spelling {replacement!r} instead of {match.group()!r}.",
                byte_range=byte_range,
            )
        )
    return findings


def _parenthesis_findings(text: str, excluded: tuple[ByteRange, ...]) -> list[Finding]:
    offsets = char_to_byte_offsets(text)
    stack: list[int] = []
    findings: list[Finding] = []
    for index, character in enumerate(text):
        character_range = ByteRange(start=offsets[index], end=offsets[index + 1])
        if _overlaps(character_range, excluded):
            continue
        if character == "(":
            stack.append(index)
        elif character == ")":
            if stack:
                stack.pop()
            else:
                findings.append(
                    _finding(
                        text,
                        rule_id="8.3",
                        message="Closing parenthesis has no matching opening parenthesis.",
                        byte_range=character_range,
                    )
                )
    for index in stack:
        findings.append(
            _finding(
                text,
                rule_id="8.3",
                message="Opening parenthesis has no matching closing parenthesis.",
                byte_range=ByteRange(start=offsets[index], end=offsets[index + 1]),
            )
        )
    return findings


def _project_matches(text: str, project: ProjectDictionary | None) -> tuple[TermMatch, ...]:
    return () if project is None else TermMatcher(project).find(text)


def _overlaps(byte_range: ByteRange, ranges: tuple[ByteRange, ...]) -> bool:
    return any(byte_range.start < item.end and item.start < byte_range.end for item in ranges)


def _is_protected(byte_range: ByteRange, ranges: tuple[ByteRange, ...]) -> bool:
    return any(item.start <= byte_range.start and byte_range.end <= item.end for item in ranges)


def _dictionary_expression_pattern(expression: str) -> re.Pattern[str]:
    pieces = expression.split("...")
    body = r"\s+[\w-]+(?:\s+[\w-]+)*?\s+".join(
        re.escape(piece.strip()).replace(r"\ ", r"\s+") for piece in pieces
    )
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", re.IGNORECASE)


def _dictionary_phrase_findings(  # noqa: C901 -- Approved and unapproved phrase dispatch.
    text: str,
    standard: StandardPack,
    project_ranges: tuple[ByteRange, ...],
) -> tuple[list[Finding], tuple[ByteRange, ...]]:
    grouped: dict[str, list[DictionaryEntry]] = {}
    for entry in standard.dictionary:
        expressions = (
            (entry.qualifier,)
            if entry.qualifier is not None
            else (entry.word, *entry.approved_forms)
        )
        for expression in expressions:
            if " " in expression:
                grouped.setdefault(expression, []).append(entry)
    phrases = sorted(
        grouped.items(),
        key=lambda item: (0 if "..." in item[0] else 1, -len(item[0]), item[0]),
    )
    if not phrases:
        return [], ()
    offsets = char_to_byte_offsets(text)
    occupied: list[ByteRange] = []
    findings: list[Finding] = []
    for phrase, entries in phrases:
        pattern = _dictionary_expression_pattern(phrase)
        for match in pattern.finditer(text):
            byte_range = ByteRange(start=offsets[match.start()], end=offsets[match.end()])
            if _overlaps(byte_range, (*project_ranges, *occupied)):
                continue
            occupied.append(byte_range)
            matched_entries = tuple(
                {
                    entry.entry_id: entry
                    for entry in (*entries, *grouped.get(match.group().casefold(), ()))
                }.values()
            )
            approved = tuple(entry for entry in matched_entries if entry.status == "approved")
            unapproved = tuple(entry for entry in matched_entries if entry.status == "unapproved")
            if approved and unapproved:
                findings.append(
                    _finding_for_rules(
                        text,
                        rule_ids=("1.1", "1.6"),
                        message=(
                            f"{match.group()!r} has both approved and unapproved "
                            "dictionary entries."
                        ),
                        byte_range=byte_range,
                    )
                )
            elif unapproved:
                findings.extend(_unapproved_findings(text, match.group(), byte_range, unapproved))
    return findings, tuple(occupied)


def _unapproved_findings(
    text: str,
    token: str,
    byte_range: ByteRange,
    entries: tuple[DictionaryEntry, ...],
) -> list[Finding]:
    alternatives = sorted({alternative for entry in entries for alternative in entry.alternatives})
    suffix = f" Use: {', '.join(alternatives)}." if alternatives else ""
    return [
        _finding_for_rules(
            text,
            rule_ids=("1.1", "1.6"),
            message=f"{token!r} is listed as unapproved.{suffix}",
            byte_range=byte_range,
        )
    ]


def _linguistically_approved_ranges(
    sentences: tuple[LinguisticSentence, ...], standard: StandardPack
) -> tuple[ByteRange, ...]:
    index = standard.dictionary_by_word
    approved = []
    for sentence in sentences:
        for token in sentence.tokens:
            actual_pos = _SPACY_POS.get(token.pos)
            if actual_pos is None:
                continue
            entries = index.get(token.text.casefold(), ())
            if any(
                entry.status == "approved" and actual_pos in entry.parts_of_speech
                for entry in entries
            ):
                approved.append(token.byte_range)
    return tuple(approved)


def _vocabulary_findings(
    document: Document,
    standard: StandardPack,
    excluded: tuple[ByteRange, ...],
    linguistically_approved: tuple[ByteRange, ...],
) -> list[Finding]:
    findings, phrase_ranges = _dictionary_phrase_findings(document.text, standard, excluded)
    index = standard.dictionary_by_word
    for sentence in document.sentences:
        for token in sentence.tokens:
            if (
                not _LEXICAL_RE.fullmatch(token.text)
                or _overlaps(token.byte_range, excluded)
                or _overlaps(token.byte_range, phrase_ranges)
            ):
                continue
            entries = index.get(token.text.casefold(), ())
            approved = tuple(entry for entry in entries if entry.status == "approved")
            unapproved = tuple(entry for entry in entries if entry.status == "unapproved")
            if approved and unapproved and not _overlaps(token.byte_range, linguistically_approved):
                findings.append(
                    _finding_for_rules(
                        document.text,
                        rule_ids=("1.1", "1.6"),
                        message=(
                            f"{token.text!r} has both approved and unapproved dictionary entries."
                        ),
                        byte_range=token.byte_range,
                    )
                )
            elif approved:
                continue
            elif unapproved:
                findings.extend(
                    _unapproved_findings(document.text, token.text, token.byte_range, unapproved)
                )
            else:
                findings.append(
                    _finding(
                        document.text,
                        rule_id="1.1",
                        message=(
                            f"{token.text!r} is not in the extracted STE dictionary "
                            "or the supplied project dictionary."
                        ),
                        byte_range=token.byte_range,
                    )
                )
    return findings


def _sentence_limit_findings(
    document: Document,
    block: Block,
    *,
    rule_id: str,
    label: str,
    maximum: int,
    excluded: tuple[ByteRange, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    for sentence in block.sentences:
        if _is_protected(sentence.byte_range, excluded):
            continue
        word_count = sum(not _overlaps(token.byte_range, excluded) for token in sentence.tokens)
        if word_count <= maximum or _GROUPED_ELEMENT_RE.search(sentence.text) is not None:
            continue
        findings.append(
            _finding(
                document.text,
                rule_id=rule_id,
                message=f"{label} has {word_count} words; maximum {maximum}.",
                byte_range=sentence.byte_range,
            )
        )
    return findings


def _structure_findings(document: Document, excluded: tuple[ByteRange, ...]) -> list[Finding]:
    findings: list[Finding] = []
    for block in document.blocks:
        if _is_protected(block.byte_range, excluded):
            continue
        if block.kind in {BlockKind.PROCEDURE, BlockKind.WARNING, BlockKind.CAUTION}:
            findings.extend(
                _sentence_limit_findings(
                    document,
                    block,
                    rule_id="5.1",
                    label="Procedure sentence",
                    maximum=20,
                    excluded=excluded,
                )
            )
        if block.kind in {BlockKind.PARAGRAPH, BlockKind.NOTE}:
            findings.extend(
                _sentence_limit_findings(
                    document,
                    block,
                    rule_id="6.3",
                    label="Descriptive sentence",
                    maximum=25,
                    excluded=excluded,
                )
            )
        if block.kind is BlockKind.PARAGRAPH:
            visible_sentences = tuple(
                sentence
                for sentence in block.sentences
                if not _is_protected(sentence.byte_range, excluded)
            )
            if len(visible_sentences) > 6:
                findings.append(
                    _finding(
                        document.text,
                        rule_id="6.6",
                        message=f"Paragraph has {len(visible_sentences)} sentences; maximum 6.",
                        byte_range=block.byte_range,
                    )
                )
    return findings


def _list_findings(text: str, excluded: tuple[ByteRange, ...]) -> list[Finding]:
    offsets = char_to_byte_offsets(text)
    findings: list[Finding] = []
    for match in _LIST_WITHOUT_COLON_RE.finditer(text):
        intro_range = ByteRange(
            start=offsets[match.start("intro")], end=offsets[match.end("intro")]
        )
        if _overlaps(intro_range, excluded):
            continue
        findings.append(
            _finding(
                text,
                rule_id="4.3",
                message="Use a colon before a vertical list.",
                byte_range=intro_range,
            )
        )
    return findings


def _block_for_token(document: Document, token: LinguisticToken) -> Block | None:
    return next(
        (
            block
            for block in document.blocks
            if block.byte_range.start <= token.byte_range.start < block.byte_range.end
        ),
        None,
    )


def _is_imperative(sentence: LinguisticSentence) -> bool:
    tokens = sentence.tokens
    if tokens and tokens[0].text.upper() in {"CAUTION", "NOTE", "WARNING"}:
        colon = next((index for index, token in enumerate(tokens) if token.text == ":"), None)
        if colon is not None:
            tokens = tokens[colon + 1 :]
    roots = [
        token for token in tokens if token.dependency == "ROOT" and token.pos in {"AUX", "VERB"}
    ]
    if not roots:
        roots = [
            token
            for token in tokens
            if token.dependency == "xcomp" and token.pos in {"AUX", "VERB"}
        ]
    if len(roots) != 1 or roots[0].tag != "VB":
        return False
    root = roots[0]
    return not any(
        token.dependency in {"nsubj", "nsubjpass"} and token.head_index == root.token_index
        for token in tokens
    )


def _visible_linguistic_tokens(
    sentence: LinguisticSentence,
    protected: tuple[ByteRange, ...],
    project_ranges: tuple[ByteRange, ...],
    code_ranges: tuple[ByteRange, ...],
) -> tuple[LinguisticToken, ...]:
    return tuple(
        token
        for token in sentence.tokens
        if not _overlaps(token.byte_range, code_ranges)
        and (
            not _overlaps(token.byte_range, protected)
            or _overlaps(token.byte_range, project_ranges)
        )
    )


def _passive_findings(
    document: Document,
    sentence: LinguisticSentence,
    block: Block | None,
) -> list[Finding]:
    if block is None or block.kind is not BlockKind.PROCEDURE:
        return []
    constructions: dict[int, LinguisticToken] = {}
    for token in sentence.tokens:
        if token.dependency in {"auxpass", "nsubjpass"}:
            constructions.setdefault(token.head_index, token)
    return [
        _finding(
            document.text,
            rule_id="3.6",
            message="Procedure uses passive voice; use active voice.",
            byte_range=token.byte_range,
        )
        for token in constructions.values()
    ]


def _linguistic_findings(
    document: Document,
    standard: StandardPack,
    project: ProjectDictionary | None,
    sentences: tuple[LinguisticSentence, ...],
    protected: tuple[ByteRange, ...],
    code_ranges: tuple[ByteRange, ...],
) -> list[Finding]:
    if not sentences:
        return []
    findings: list[Finding] = []
    project_matches = _project_matches(document.text, project)
    project_ranges = tuple(match.byte_range for match in project_matches)
    index = standard.dictionary_by_word
    for sentence in sentences:
        syntax_incomplete = any(
            _overlaps(token.byte_range, code_ranges) for token in sentence.tokens
        )
        visible_tokens = _visible_linguistic_tokens(
            sentence, protected, project_ranges, code_ranges
        )
        if not visible_tokens:
            continue
        sentence = LinguisticSentence(
            text=sentence.text,
            tokens=visible_tokens,
            byte_range=sentence.byte_range,
        )
        imperative = _is_imperative(sentence)
        sentence_block = _block_for_token(document, sentence.tokens[0])
        findings.extend(_passive_findings(document, sentence, sentence_block))
        if (
            not syntax_incomplete
            and sentence_block is not None
            and sentence_block.kind is BlockKind.PROCEDURE
            and not imperative
        ):
            findings.append(
                _finding(
                    document.text,
                    rule_id="5.3",
                    message="Write the procedure step in the imperative form.",
                    byte_range=sentence.byte_range,
                )
            )
        if (
            not syntax_incomplete
            and sentence_block is not None
            and sentence_block.kind is BlockKind.NOTE
            and imperative
        ):
            findings.append(
                _finding(
                    document.text,
                    rule_id="5.5",
                    message="Use notes for information, not instructions.",
                    byte_range=sentence.byte_range,
                )
            )
        if (
            not syntax_incomplete
            and sentence_block is not None
            and sentence_block.kind in {BlockKind.WARNING, BlockKind.CAUTION}
            and not imperative
            and not re.match(
                r"^\s*(?:WARNING|CAUTION):\s*(?:if|when|before|after)\b",
                sentence.text,
                re.IGNORECASE,
            )
        ):
            findings.append(
                _finding(
                    document.text,
                    rule_id="7.2",
                    message="Start the safety instruction with a command or condition.",
                    byte_range=sentence.byte_range,
                )
            )
        for token in sentence.tokens:
            findings.extend(
                _token_linguistic_findings(
                    document,
                    token,
                    index,
                    project,
                    project_matches,
                )
            )
    return findings


def _token_linguistic_findings(
    document: Document,
    token: LinguisticToken,
    index: dict[str, tuple[DictionaryEntry, ...]],
    project: ProjectDictionary | None,
    project_matches: tuple[TermMatch, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    owner = next(
        (
            match.term
            for match in project_matches
            if _overlaps(token.byte_range, (match.byte_range,))
        ),
        None,
    )
    actual_pos = _SPACY_POS.get(token.pos)
    entries = index.get(token.text.casefold(), ())
    approved = tuple(entry for entry in entries if entry.status == "approved")
    if (
        owner is None
        and actual_pos is not None
        and approved
        and not any(actual_pos in entry.parts_of_speech for entry in approved)
    ):
        findings.append(
            _finding(
                document.text,
                rule_id="1.2",
                message=f"{token.text!r} is not approved as a {actual_pos}.",
                byte_range=token.byte_range,
            )
        )
    unapproved_for_pos = tuple(
        entry
        for entry in entries
        if entry.status == "unapproved" and actual_pos in entry.parts_of_speech
    )
    if owner is None and actual_pos not in {None, "noun", "verb"} and unapproved_for_pos:
        findings.append(
            _finding_for_rules(
                document.text,
                rule_ids=("1.1", "1.6"),
                message=f"{token.text!r} is unapproved as a {actual_pos}.",
                byte_range=token.byte_range,
            )
        )
    lemma_entries = tuple(
        entry
        for entry in index.get(token.lemma, ())
        if entry.status == "approved" and actual_pos in entry.parts_of_speech
    )
    if owner is None and token.pos in {"VERB", "ADJ"} and lemma_entries:
        allowed = {
            value.casefold()
            for entry in lemma_entries
            for value in (entry.word, *entry.approved_forms)
        }
        if token.text.casefold() not in allowed:
            rule_id = "3.1" if token.pos == "VERB" else "1.4"
            findings.append(
                _finding(
                    document.text,
                    rule_id=rule_id,
                    message=f"{token.text!r} is not a listed approved form of {token.lemma!r}.",
                    byte_range=token.byte_range,
                )
            )
    if project is not None:
        if owner is not None and owner.category == "technical_noun" and token.pos == "VERB":
            findings.append(
                _finding(
                    document.text,
                    rule_id="1.7",
                    message=f"Do not use technical noun {owner.term!r} as a verb.",
                    byte_range=token.byte_range,
                )
            )
        if owner is not None and owner.category == "technical_verb" and token.pos == "NOUN":
            findings.append(
                _finding(
                    document.text,
                    rule_id="1.13",
                    message=f"Do not use technical verb {owner.term!r} as a noun.",
                    byte_range=token.byte_range,
                )
            )
    return findings


def _merge_findings(findings: list[Finding]) -> tuple[Finding, ...]:
    grouped: dict[tuple[int, int], list[Finding]] = {}
    for finding in findings:
        key = (finding.byte_range.start, finding.byte_range.end)
        grouped.setdefault(key, []).append(finding)
    merged = []
    for items in grouped.values():
        first = items[0]
        rule_ids = tuple(dict.fromkeys(rule_id for item in items for rule_id in item.rule_ids))
        messages = tuple(dict.fromkeys(item.message for item in items))
        merged.append(
            Finding(
                rule_ids=rule_ids,
                message=" ".join(messages),
                byte_range=first.byte_range,
                excerpt=first.excerpt,
            )
        )
    return tuple(
        sorted(
            merged,
            key=lambda item: (item.byte_range.start, item.byte_range.end, item.rule_ids),
        )
    )


def analyze(
    text: str,
    *,
    standard: StandardPack | None = None,
    project_dictionary: ProjectDictionary | None = None,
    linguistic_analyzer: LinguisticAnalyzer | None = None,
) -> AnalysisResult:
    """Analyze text without making an official compliance claim."""

    standard = standard or load_bundled_standard()
    if project_dictionary is not None:
        report = validate_project_dictionary(project_dictionary)
        if not report.valid:
            details = "; ".join(issue.message for issue in report.issues)
            raise ValueError(f"invalid project dictionary: {details}")
    document = parse_document(text)
    protected_ranges = _protected_ranges(text, project_dictionary)
    code_ranges = _pattern_ranges(text, _CODE_RE)
    linguistic_sentences = () if linguistic_analyzer is None else linguistic_analyzer.analyze(text)
    linguistically_approved = _linguistically_approved_ranges(linguistic_sentences, standard)
    findings: list[Finding] = []
    findings.extend(
        _regex_findings(
            text,
            re.compile(";"),
            rule_id="8.1",
            message="Do not use a semicolon.",
            excluded=protected_ranges,
        )
    )
    findings.extend(
        _regex_findings(
            text,
            _CONTRACTION_RE,
            rule_id="4.2",
            message="Do not use a contraction.",
            excluded=protected_ranges,
        )
    )
    findings.extend(_spelling_findings(text, protected_ranges))
    findings.extend(_parenthesis_findings(text, protected_ranges))
    findings.extend(_list_findings(text, code_ranges))
    findings.extend(
        _vocabulary_findings(
            document,
            standard,
            protected_ranges,
            linguistically_approved,
        )
    )
    findings.extend(_structure_findings(document, code_ranges))
    findings.extend(
        _linguistic_findings(
            document,
            standard,
            project_dictionary,
            linguistic_sentences,
            protected_ranges,
            code_ranges,
        )
    )
    ordered = _merge_findings(findings)
    return AnalysisResult(
        standard_id="ASD-STE100",
        standard_issue=9,
        standard_digest=standard.manifest.source.source_digest,
        passed=not ordered,
        findings=ordered,
    )
