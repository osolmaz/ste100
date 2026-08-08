"""Deterministic analysis with explicit rule-by-rule coverage."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from ste100.document import (
    Block,
    BlockKind,
    Document,
    char_to_byte_offsets,
    parse_document,
    slice_bytes,
)
from ste100.linguistics import LinguisticAnalyzer, LinguisticSentence, LinguisticToken
from ste100.models import (
    AnalysisResult,
    ByteRange,
    CoverageStatus,
    DictionaryEntry,
    Finding,
    FindingKind,
    ProjectDictionary,
    RuleCoverage,
)
from ste100.rule_ids import ISSUE9_RULE_IDS
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
_LATIN_ABBREVIATION_RE = re.compile(r"(?<!\w)(?:e\.g\.|i\.e\.|etc\.|et al\.)(?!\w)", re.I)
_GENDERED_RE = re.compile(
    r"\b(?:he|she|him|her|his|hers|himself|herself|manpower|man-hours?|mankind)\b",
    re.IGNORECASE,
)
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
_ALWAYS_APPLICABLE = frozenset({"1.1", "1.14", "4.2", "8.1", "8.3", "GR-6", "GR-7"})
_LINGUISTIC_RULE_IDS = frozenset(
    {
        "1.2",
        "1.4",
        "1.7",
        "1.13",
        "3.1",
        "3.2",
        "3.4",
        "3.5",
        "3.6",
        "5.2",
        "5.3",
        "5.5",
        "7.2",
        "GR-1",
    }
)


def _finding_id(rule_id: str, checker_id: str, byte_range: ByteRange | None, message: str) -> str:
    location = "none" if byte_range is None else f"{byte_range.start}:{byte_range.end}"
    raw = f"{rule_id}\0{checker_id}\0{location}\0{message}".encode()
    return f"finding_{hashlib.sha256(raw).hexdigest()[:16]}"


def _finding(
    text: str,
    *,
    rule_id: str,
    checker_id: str,
    kind: FindingKind,
    message: str,
    byte_range: ByteRange | None,
) -> Finding:
    return Finding(
        finding_id=_finding_id(rule_id, checker_id, byte_range, message),
        rule_id=rule_id,
        kind=kind,
        message=message,
        byte_range=byte_range,
        excerpt=slice_bytes(text, byte_range) if byte_range is not None else None,
        checker_id=checker_id,
    )


def _regex_findings(
    text: str,
    pattern: re.Pattern[str],
    *,
    rule_id: str,
    checker_id: str,
    message: str,
    kind: FindingKind = FindingKind.VIOLATION,
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
                checker_id=checker_id,
                kind=kind,
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
                checker_id="american_spelling",
                kind=FindingKind.VIOLATION,
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
                        checker_id="balanced_parentheses",
                        kind=FindingKind.VIOLATION,
                        message="Closing parenthesis has no matching opening parenthesis.",
                        byte_range=character_range,
                    )
                )
    for index in stack:
        findings.append(
            _finding(
                text,
                rule_id="8.3",
                checker_id="balanced_parentheses",
                kind=FindingKind.VIOLATION,
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
                    _finding(
                        text,
                        rule_id="1.1",
                        checker_id="vocabulary",
                        kind=FindingKind.HUMAN_REVIEW,
                        message=f"Review the part of speech and meaning of {match.group()!r}.",
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
    message = (
        f"{token!r} is listed as unapproved.{suffix} "
        "Review whether this use is approved project terminology."
    )
    return [
        _finding(
            text,
            rule_id=rule_id,
            checker_id="vocabulary" if rule_id == "1.1" else "unapproved_vocabulary",
            kind=FindingKind.HUMAN_REVIEW,
            message=message,
            byte_range=byte_range,
        )
        for rule_id in ("1.1", "1.6")
    ]


def _vocabulary_findings(
    document: Document,
    standard: StandardPack,
    excluded: tuple[ByteRange, ...],
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
            if approved and unapproved:
                findings.append(
                    _finding(
                        document.text,
                        rule_id="1.1",
                        checker_id="vocabulary",
                        kind=FindingKind.HUMAN_REVIEW,
                        message=f"Review the part of speech and meaning of {token.text!r}.",
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
                        checker_id="vocabulary",
                        kind=FindingKind.HUMAN_REVIEW,
                        message=f"Review {token.text!r} as possible project terminology.",
                        byte_range=token.byte_range,
                    )
                )
    return findings


def _sentence_limit_findings(
    document: Document,
    block: Block,
    *,
    rule_id: str,
    checker_id: str,
    label: str,
    maximum: int,
    excluded: tuple[ByteRange, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    for sentence in block.sentences:
        if _is_protected(sentence.byte_range, excluded):
            continue
        word_count = sum(not _overlaps(token.byte_range, excluded) for token in sentence.tokens)
        if word_count <= maximum:
            continue
        uncertain = _GROUPED_ELEMENT_RE.search(sentence.text) is not None
        message = f"{label} has a mechanical count of {word_count}; maximum {maximum}."
        if uncertain:
            message += " Review possible Rule 8.6 grouped elements."
        findings.append(
            _finding(
                document.text,
                rule_id=rule_id,
                checker_id=checker_id,
                kind=FindingKind.HUMAN_REVIEW if uncertain else FindingKind.VIOLATION,
                message=message,
                byte_range=sentence.byte_range,
            )
        )
    return findings


def _condition_comma_findings(
    document: Document, block: Block, excluded: tuple[ByteRange, ...]
) -> list[Finding]:
    findings: list[Finding] = []
    for sentence in block.sentences:
        if _is_protected(sentence.byte_range, excluded):
            continue
        if not re.match(
            r"^\s*(?:\d+(?:\.\d+)*[.)]\s*)?(?:if|when|before|after|while|unless)\b",
            sentence.text,
            re.IGNORECASE,
        ):
            continue
        first_command = sentence.text.find(",")
        if first_command >= 0:
            continue
        findings.append(
            _finding(
                document.text,
                rule_id="5.4",
                checker_id="condition_comma",
                kind=FindingKind.HUMAN_REVIEW,
                message="Review whether an initial condition and command need a separating comma.",
                byte_range=sentence.byte_range,
            )
        )
    return findings


def _structure_findings(  # noqa: C901 -- Explicit block-kind dispatch.
    document: Document, excluded: tuple[ByteRange, ...]
) -> tuple[list[Finding], set[str]]:
    findings: list[Finding] = []
    applicable: set[str] = set(_ALWAYS_APPLICABLE if document.text.strip() else ())
    offsets = char_to_byte_offsets(document.text)
    for match in _VERTICAL_LIST_PRESENT_RE.finditer(document.text):
        match_range = ByteRange(start=offsets[match.start()], end=offsets[match.end()])
        if not _is_protected(match_range, excluded):
            applicable.update(("4.3", "8.4"))
    for block in document.blocks:
        if _is_protected(block.byte_range, excluded):
            continue
        if block.kind in {BlockKind.PROCEDURE, BlockKind.WARNING, BlockKind.CAUTION}:
            applicable.update(("5.1", "5.2", "5.3", "5.4", "7.1", "7.2"))
            findings.extend(
                _sentence_limit_findings(
                    document,
                    block,
                    rule_id="5.1",
                    checker_id="procedure_sentence_length",
                    label="Procedure sentence",
                    maximum=20,
                    excluded=excluded,
                )
            )
            findings.extend(_condition_comma_findings(document, block, excluded))
        if block.kind in {BlockKind.PARAGRAPH, BlockKind.NOTE}:
            applicable.add("6.3")
            findings.extend(
                _sentence_limit_findings(
                    document,
                    block,
                    rule_id="6.3",
                    checker_id="descriptive_sentence_length",
                    label="Descriptive sentence",
                    maximum=25,
                    excluded=excluded,
                )
            )
        if block.kind is BlockKind.PARAGRAPH:
            applicable.add("6.6")
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
                        checker_id="paragraph_sentence_count",
                        kind=FindingKind.VIOLATION,
                        message=f"Paragraph has {len(visible_sentences)} sentences; maximum 6.",
                        byte_range=block.byte_range,
                    )
                )
        if block.kind is BlockKind.NOTE:
            applicable.add("5.5")
        if block.kind is BlockKind.LIST:
            applicable.update(("4.3", "8.4"))
    if any(not _is_protected(sentence.byte_range, excluded) for sentence in document.sentences):
        applicable.update(("8.5", "8.6", "8.7"))
    return findings, applicable


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
                checker_id="vertical_list",
                kind=FindingKind.VIOLATION,
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


def _omits_that_before_finite_clause(sentence: LinguisticSentence) -> bool:
    lemmas = [token.lemma for token in sentence.tokens]
    trigger = any(lemma in {"recommend", "show"} for lemma in lemmas) or any(
        lemmas[index : index + 2] == ["make", "sure"] for index in range(len(lemmas) - 1)
    )
    finite_clause = any(token.dependency == "ccomp" for token in sentence.tokens)
    explicit_that = any(
        token.lemma == "that" and token.dependency == "mark" for token in sentence.tokens
    )
    return trigger and finite_clause and not explicit_that


def _omitted_that_findings(document: Document, sentence: LinguisticSentence) -> list[Finding]:
    if not _omits_that_before_finite_clause(sentence):
        return []
    return [
        _finding(
            document.text,
            rule_id="GR-1",
            checker_id="omitted_that",
            kind=FindingKind.HUMAN_REVIEW,
            message="Consider 'that' before this subordinate clause to prevent ambiguity.",
            byte_range=sentence.byte_range,
        )
    ]


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


def _linguistic_findings(  # noqa: C901 -- Independent sentence-level checks.
    document: Document,
    standard: StandardPack,
    project: ProjectDictionary | None,
    analyzer: LinguisticAnalyzer | None,
    protected: tuple[ByteRange, ...],
    code_ranges: tuple[ByteRange, ...],
) -> tuple[list[Finding], set[str]]:
    applicable = (
        set(_LINGUISTIC_RULE_IDS)
        if any(
            not _is_protected(sentence.byte_range, code_ranges) for sentence in document.sentences
        )
        else set()
    )
    if analyzer is None:
        return [], applicable
    findings: list[Finding] = []
    project_matches = _project_matches(document.text, project)
    project_ranges = tuple(match.byte_range for match in project_matches)
    index = standard.dictionary_by_word
    for sentence in analyzer.analyze(document.text):
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
        sentence_block = _block_for_token(document, sentence.tokens[0]) if sentence.tokens else None
        findings.extend(_omitted_that_findings(document, sentence))
        if (
            sentence_block is not None
            and sentence_block.kind is BlockKind.PROCEDURE
            and not imperative
        ):
            findings.append(
                _finding(
                    document.text,
                    rule_id="5.3",
                    checker_id="imperative_instruction",
                    kind=FindingKind.VIOLATION,
                    message="Write the procedure step in the imperative form.",
                    byte_range=sentence.byte_range,
                )
            )
        if sentence_block is not None and sentence_block.kind is BlockKind.NOTE and imperative:
            findings.append(
                _finding(
                    document.text,
                    rule_id="5.5",
                    checker_id="note_instruction",
                    kind=FindingKind.VIOLATION,
                    message="Use notes for information, not instructions.",
                    byte_range=sentence.byte_range,
                )
            )
        if (
            sentence_block is not None
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
                    checker_id="safety_opening",
                    kind=FindingKind.HUMAN_REVIEW,
                    message="Start the safety instruction with a clear command or condition.",
                    byte_range=sentence.byte_range,
                )
            )
        verb_actions = [
            token
            for token in sentence.tokens
            if token.pos == "VERB" and token.dependency in {"ROOT", "conj"}
        ]
        if (
            sentence_block is not None
            and sentence_block.kind is BlockKind.PROCEDURE
            and len(verb_actions) > 1
        ):
            findings.append(
                _finding(
                    document.text,
                    rule_id="5.2",
                    checker_id="instruction_count",
                    kind=FindingKind.HUMAN_REVIEW,
                    message="Review whether the procedure sentence contains simultaneous actions.",
                    byte_range=sentence.byte_range,
                )
            )
        for token in sentence.tokens:
            findings.extend(
                _token_linguistic_findings(
                    document,
                    token,
                    sentence_block,
                    index,
                    project,
                    project_matches,
                    project_ranges,
                )
            )
    return findings, applicable


def _token_linguistic_findings(  # noqa: C901 -- Independent linguistic clauses.
    document: Document,
    token: LinguisticToken,
    block: Block | None,
    index: dict[str, tuple[DictionaryEntry, ...]],
    project: ProjectDictionary | None,
    project_matches: tuple[TermMatch, ...],
    project_ranges: tuple[ByteRange, ...],
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
                checker_id="approved_part_of_speech",
                kind=FindingKind.VIOLATION,
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
        for rule_id, checker_id in (("1.1", "vocabulary_pos"), ("1.6", "unapproved_pos")):
            findings.append(
                _finding(
                    document.text,
                    rule_id=rule_id,
                    checker_id=checker_id,
                    kind=FindingKind.VIOLATION,
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
                    checker_id="approved_form",
                    kind=FindingKind.VIOLATION,
                    message=f"{token.text!r} is not a listed approved form of {token.lemma!r}.",
                    byte_range=token.byte_range,
                )
            )
    if token.tag == "VBG" and not _overlaps(token.byte_range, project_ranges):
        for rule_id, checker_id in (("3.2", "verb_form"), ("3.5", "ing_form")):
            findings.append(
                _finding(
                    document.text,
                    rule_id=rule_id,
                    checker_id=checker_id,
                    kind=FindingKind.HUMAN_REVIEW,
                    message=(
                        "Review whether this -ing form is an approved technical noun or modifier."
                    ),
                    byte_range=token.byte_range,
                )
            )
    if token.dependency in {"auxpass", "nsubjpass"}:
        kind = (
            FindingKind.VIOLATION
            if block is not None and block.kind is BlockKind.PROCEDURE
            else FindingKind.HUMAN_REVIEW
        )
        findings.append(
            _finding(
                document.text,
                rule_id="3.6",
                checker_id="passive_voice",
                kind=kind,
                message="Review passive voice; procedures must use active voice.",
                byte_range=token.byte_range,
            )
        )
    if token.tag in {"VBG", "VBN"} and token.dependency in {"xcomp", "ccomp"}:
        findings.append(
            _finding(
                document.text,
                rule_id="3.4",
                checker_id="complex_verb",
                kind=FindingKind.HUMAN_REVIEW,
                message="Review this possible complex verb construction.",
                byte_range=token.byte_range,
            )
        )
    if project is not None:
        if owner is not None and owner.category == "technical_noun" and token.pos == "VERB":
            findings.append(
                _finding(
                    document.text,
                    rule_id="1.7",
                    checker_id="technical_noun_as_verb",
                    kind=FindingKind.VIOLATION,
                    message=f"Do not use technical noun {owner.term!r} as a verb.",
                    byte_range=token.byte_range,
                )
            )
        if owner is not None and owner.category == "technical_verb" and token.pos == "NOUN":
            findings.append(
                _finding(
                    document.text,
                    rule_id="1.13",
                    checker_id="technical_verb_as_noun",
                    kind=FindingKind.VIOLATION,
                    message=f"Do not use technical verb {owner.term!r} as a noun.",
                    byte_range=token.byte_range,
                )
            )
    return findings


def _coverage(
    findings: tuple[Finding, ...],
    *,
    applicable: set[str],
    standard: StandardPack,
) -> tuple[RuleCoverage, ...]:
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_rule[finding.rule_id].append(finding)
    matrix = {item.rule_id: item for item in standard.conformance}
    treatments = {item.rule_id: item.treatment for item in standard.rules}
    records: list[RuleCoverage] = []
    for rule_id in ISSUE9_RULE_IDS:
        rule_findings = by_rule.get(rule_id, [])
        ids = tuple(item.finding_id for item in rule_findings)
        if any(item.kind is FindingKind.VIOLATION for item in rule_findings):
            status = CoverageStatus.FAILED
            reason = None
        elif rule_findings:
            status = CoverageStatus.HUMAN_REVIEW
            reason = "The deterministic evidence is not conclusive."
        else:
            conformance = matrix[rule_id]
            if conformance.coverage_scope == "none":
                status = CoverageStatus.HUMAN_REVIEW
                reason = conformance.reason
            elif rule_id not in applicable:
                status = CoverageStatus.NOT_APPLICABLE
                reason = "No applicable structure was found."
            elif conformance.coverage_scope == "full":
                status = CoverageStatus.PASSED
                reason = None
            else:
                status = CoverageStatus.HUMAN_REVIEW
                reason = conformance.reason
        records.append(
            RuleCoverage(
                rule_id=rule_id,
                treatment=treatments[rule_id],
                status=status,
                finding_ids=ids,
                reason=reason,
            )
        )
    return tuple(records)


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
    findings: list[Finding] = []
    findings.extend(
        _regex_findings(
            text,
            re.compile(";"),
            rule_id="8.1",
            checker_id="semicolon",
            message="Do not use a semicolon.",
            excluded=protected_ranges,
        )
    )
    findings.extend(
        _regex_findings(
            text,
            _CONTRACTION_RE,
            rule_id="4.2",
            checker_id="contraction",
            message="Do not use a contraction.",
            excluded=protected_ranges,
        )
    )
    findings.extend(_spelling_findings(text, protected_ranges))
    findings.extend(
        _regex_findings(
            text,
            _LATIN_ABBREVIATION_RE,
            rule_id="GR-6",
            checker_id="latin_abbreviation",
            message="Write the expression in full instead of a Latin abbreviation.",
            kind=FindingKind.HUMAN_REVIEW,
            excluded=protected_ranges,
        )
    )
    findings.extend(
        _regex_findings(
            text,
            _GENDERED_RE,
            rule_id="GR-7",
            checker_id="gendered_term",
            message="Use neutral and inclusive wording.",
            kind=FindingKind.HUMAN_REVIEW,
            excluded=protected_ranges,
        )
    )
    findings.extend(_parenthesis_findings(text, protected_ranges))
    findings.extend(_list_findings(text, code_ranges))
    findings.extend(_vocabulary_findings(document, standard, protected_ranges))
    structure_findings, applicable = _structure_findings(document, code_ranges)
    findings.extend(structure_findings)
    linguistic_findings, linguistic_applicable = _linguistic_findings(
        document,
        standard,
        project_dictionary,
        linguistic_analyzer,
        protected_ranges,
        code_ranges,
    )
    findings.extend(linguistic_findings)
    applicable.update(linguistic_applicable)
    if project_dictionary is not None:
        applicable.update(("1.8", "1.11", "2.1", "9.4"))
    ordered = tuple(
        sorted(
            findings,
            key=lambda item: (
                item.byte_range.start if item.byte_range is not None else -1,
                item.rule_id,
                item.finding_id,
            ),
        )
    )
    return AnalysisResult(
        standard_id="ASD-STE100",
        standard_issue=9,
        standard_digest=standard.manifest.source.source_digest,
        findings=ordered,
        coverage=_coverage(ordered, applicable=applicable, standard=standard),
    )
