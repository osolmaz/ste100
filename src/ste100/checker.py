"""Deterministic analysis with explicit rule-by-rule coverage."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from ste100.contracts import Detector
from ste100.document import (
    Block,
    BlockKind,
    Document,
    char_to_byte_offsets,
    parse_document,
    slice_bytes,
)
from ste100.models import (
    AnalysisResult,
    ByteRange,
    CoverageStatus,
    Finding,
    FindingKind,
    ProjectDictionary,
    RuleCoverage,
    RuleTreatment,
)
from ste100.standard import StandardPack
from ste100.terminology import TermMatcher, validate_project_dictionary

_APOSTROPHE = "['\u2019]"
_CONTRACTION_RE = re.compile(
    rf"\b(?:[A-Za-z]+n{_APOSTROPHE}t|[Ii]{_APOSTROPHE}m|"
    rf"[A-Za-z]+{_APOSTROPHE}(?:re|ve|ll|d)|"
    rf"(?:he|she|it|that|there|what|where|when|who|how|here|why|let){_APOSTROPHE}s)\b",
    re.IGNORECASE,
)
_LEXICAL_RE = re.compile(r"^[A-Za-z]+(?:'[A-Za-z]+)?$")
_GROUPED_ELEMENT_RE = re.compile(
    r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){1,}\b"
)
_RULE_COUNTS = {1: 14, 2: 2, 3: 7, 4: 5, 5: 5, 6: 6, 7: 3, 8: 7, 9: 4}
_ALL_RULE_IDS = tuple(
    [
        f"{section}.{number}"
        for section, count in _RULE_COUNTS.items()
        for number in range(1, count + 1)
    ]
    + [f"GR-{number}" for number in range(1, 9)]
)
_CHECKER_BY_RULE = {
    "1.1": "vocabulary",
    "4.2": "contraction",
    "5.1": "procedure_sentence_length",
    "6.3": "descriptive_sentence_length",
    "6.6": "paragraph_sentence_count",
    "8.1": "semicolon",
    "8.4": "word_count",
    "8.5": "word_count",
    "8.6": "word_count",
    "8.7": "word_count",
}
_FULL_RULES = frozenset({"6.6", "8.1", "8.4", "8.5", "8.7"})


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
    model_id: str | None = None,
    score: float | None = None,
) -> Finding:
    excerpt = slice_bytes(text, byte_range) if byte_range is not None else None
    return Finding(
        finding_id=_finding_id(rule_id, checker_id, byte_range, message),
        rule_id=rule_id,
        kind=kind,
        message=message,
        byte_range=byte_range,
        excerpt=excerpt,
        checker_id=None if model_id is not None else checker_id,
        model_id=model_id,
        score=score,
    )


def _regex_findings(
    text: str,
    pattern: re.Pattern[str],
    *,
    rule_id: str,
    checker_id: str,
    message: str,
) -> list[Finding]:
    offsets = char_to_byte_offsets(text)
    return [
        _finding(
            text,
            rule_id=rule_id,
            checker_id=checker_id,
            kind=FindingKind.VIOLATION,
            message=message,
            byte_range=ByteRange(start=offsets[match.start()], end=offsets[match.end()]),
        )
        for match in pattern.finditer(text)
    ]


def _term_ranges(text: str, project: ProjectDictionary | None) -> tuple[ByteRange, ...]:
    if project is None:
        return ()
    return tuple(match.byte_range for match in TermMatcher(project).find(text))


def _overlaps(byte_range: ByteRange, ranges: tuple[ByteRange, ...]) -> bool:
    return any(byte_range.start < item.end and item.start < byte_range.end for item in ranges)


def _vocabulary_findings(
    document: Document,
    standard: StandardPack | None,
    project: ProjectDictionary | None,
) -> list[Finding]:
    if standard is None:
        return []
    project_ranges = _term_ranges(document.text, project)
    index = standard.dictionary_by_word
    findings: list[Finding] = []
    for sentence in document.sentences:
        for token in sentence.tokens:
            if not _LEXICAL_RE.fullmatch(token.text) or _overlaps(token.byte_range, project_ranges):
                continue
            entries = index.get(token.text.casefold(), ())
            if any(entry.status == "approved" for entry in entries):
                continue
            if entries:
                alternatives = sorted(
                    {alternative for entry in entries for alternative in entry.alternatives}
                )
                suffix = f" Use: {', '.join(alternatives)}." if alternatives else ""
                findings.append(
                    _finding(
                        document.text,
                        rule_id="1.1",
                        checker_id="vocabulary",
                        kind=FindingKind.VIOLATION,
                        message=f"{token.text!r} is unapproved.{suffix}",
                        byte_range=token.byte_range,
                    )
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
) -> list[Finding]:
    findings: list[Finding] = []
    for sentence in block.sentences:
        if sentence.word_count <= maximum:
            continue
        uncertain = _GROUPED_ELEMENT_RE.search(sentence.text) is not None
        message = f"{label} has a mechanical count of {sentence.word_count}; maximum {maximum}."
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


def _paragraph_count_findings(document: Document, block: Block) -> list[Finding]:
    if len(block.sentences) <= 6:
        return []
    return [
        _finding(
            document.text,
            rule_id="6.6",
            checker_id="paragraph_sentence_count",
            kind=FindingKind.VIOLATION,
            message=f"Paragraph has {len(block.sentences)} sentences; the maximum is 6.",
            byte_range=block.byte_range,
        )
    ]


def _length_findings(document: Document) -> tuple[list[Finding], set[str]]:
    findings: list[Finding] = []
    applicable: set[str] = set()
    for block in document.blocks:
        if block.kind in {BlockKind.PROCEDURE, BlockKind.WARNING, BlockKind.CAUTION}:
            applicable.add("5.1")
            findings.extend(
                _sentence_limit_findings(
                    document,
                    block,
                    rule_id="5.1",
                    checker_id="procedure_sentence_length",
                    label="Procedure sentence",
                    maximum=20,
                )
            )
        if block.kind is BlockKind.PARAGRAPH:
            applicable.update(("6.3", "6.6"))
            findings.extend(
                _sentence_limit_findings(
                    document,
                    block,
                    rule_id="6.3",
                    checker_id="descriptive_sentence_length",
                    label="Descriptive sentence",
                    maximum=25,
                )
            )
            findings.extend(_paragraph_count_findings(document, block))
    if document.sentences:
        applicable.update(("8.4", "8.5", "8.6", "8.7"))
    return findings, applicable


def _learned_findings(text: str, detector: Detector | None) -> list[Finding]:
    if detector is None:
        return []
    findings: list[Finding] = []
    text_bytes = len(text.encode("utf-8"))
    for prediction in detector.detect(text):
        if prediction.rule_id not in _ALL_RULE_IDS:
            raise ValueError(f"detector returned unknown rule ID: {prediction.rule_id}")
        if prediction.score < 0 or prediction.score > 1:
            raise ValueError("detector score must be between 0 and 1")
        if prediction.byte_range is not None and prediction.byte_range.end > text_bytes:
            raise ValueError("detector byte range is outside the source text")
        findings.append(
            _finding(
                text,
                rule_id=prediction.rule_id,
                checker_id="learned_detector",
                kind=FindingKind.PROBABLE_VIOLATION,
                message=prediction.message,
                byte_range=prediction.byte_range,
                model_id=detector.model_id,
                score=prediction.score,
            )
        )
    return findings


def _finding_coverage(
    findings: list[Finding],
) -> tuple[CoverageStatus, str | None] | None:
    if any(item.kind is FindingKind.VIOLATION for item in findings):
        return CoverageStatus.FAILED, None
    if any(item.kind is FindingKind.PROBABLE_VIOLATION for item in findings):
        return (
            CoverageStatus.PROBABLE_VIOLATION,
            "A learned finding is report-only and does not establish nonconformance.",
        )
    if any(item.kind is FindingKind.HUMAN_REVIEW for item in findings):
        return (
            CoverageStatus.HUMAN_REVIEW,
            "The deterministic evidence is insufficient for a conclusive result.",
        )
    return None


def _empty_coverage(
    rule_id: str,
    treatment: RuleTreatment,
    applicable: set[str],
    detector: Detector | None,
) -> tuple[CoverageStatus, str | None]:
    if rule_id in _FULL_RULES and rule_id in applicable:
        return CoverageStatus.PASSED, None
    if rule_id in _FULL_RULES:
        return CoverageStatus.NOT_APPLICABLE, "No applicable structure was found."
    if rule_id in _CHECKER_BY_RULE:
        return (
            CoverageStatus.NOT_CHECKED,
            "Only a conclusive subset of this requirement is implemented.",
        )
    if treatment is RuleTreatment.HUMAN_REVIEW:
        return CoverageStatus.HUMAN_REVIEW, "This requirement needs human review."
    reason = (
        "No learned detector was supplied."
        if detector is None
        else "The detector produced no finding; absence is not a pass."
    )
    return CoverageStatus.NOT_CHECKED, reason


def _coverage(
    findings: tuple[Finding, ...],
    *,
    applicable: set[str],
    standard: StandardPack | None,
    detector: Detector | None,
) -> tuple[RuleCoverage, ...]:
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_rule[finding.rule_id].append(finding)
    treatments = (
        {rule.rule_id: rule.treatment for rule in standard.rules}
        if standard is not None
        else {
            rule_id: (
                RuleTreatment.DETERMINISTIC
                if rule_id in _CHECKER_BY_RULE
                else RuleTreatment.LEARNED
            )
            for rule_id in _ALL_RULE_IDS
        }
    )
    records: list[RuleCoverage] = []
    for rule_id in _ALL_RULE_IDS:
        rule_findings = by_rule.get(rule_id, [])
        treatment = treatments.get(rule_id, RuleTreatment.NOT_CHECKED)
        ids = tuple(item.finding_id for item in rule_findings)
        resolution = _finding_coverage(rule_findings) or _empty_coverage(
            rule_id,
            treatment,
            applicable,
            detector,
        )
        status, reason = resolution
        records.append(
            RuleCoverage(
                rule_id=rule_id,
                treatment=treatment,
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
    detector: Detector | None = None,
) -> AnalysisResult:
    """Analyze text without making an official STE compliance claim."""

    if project_dictionary is not None:
        report = validate_project_dictionary(project_dictionary, standard=standard)
        if not report.valid:
            details = "; ".join(issue.message for issue in report.issues)
            raise ValueError(f"invalid project dictionary: {details}")
    document = parse_document(text)
    findings: list[Finding] = []
    findings.extend(
        _regex_findings(
            text,
            re.compile(";"),
            rule_id="8.1",
            checker_id="semicolon",
            message="Do not use a semicolon.",
        )
    )
    findings.extend(
        _regex_findings(
            text,
            _CONTRACTION_RE,
            rule_id="4.2",
            checker_id="contraction",
            message="Do not use a contraction.",
        )
    )
    findings.extend(_vocabulary_findings(document, standard, project_dictionary))
    length_findings, applicable = _length_findings(document)
    findings.extend(length_findings)
    findings.extend(_learned_findings(text, detector))
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
    applicable.add("8.1")
    return AnalysisResult(
        standard_id="ASD-STE100",
        standard_issue=standard.manifest.issue if standard is not None else 9,
        findings=ordered,
        coverage=_coverage(
            ordered,
            applicable=applicable,
            standard=standard,
            detector=detector,
        ),
    )
