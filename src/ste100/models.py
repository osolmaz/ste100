"""Strict contracts for deterministic STE100 analysis and standard data."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
RuleId = Annotated[str, Field(pattern=r"^(?:[1-9]\d*\.[1-9]\d*|GR-[1-9]\d*)$")]


class StrictModel(BaseModel):
    """Base model that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewState(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"


class RuleTreatment(StrEnum):
    DETERMINISTIC = "deterministic"
    HUMAN_REVIEW = "human_review"


class FindingKind(StrEnum):
    VIOLATION = "violation"
    HUMAN_REVIEW = "human_review"


class CoverageStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    HUMAN_REVIEW = "human_review"
    NOT_APPLICABLE = "not_applicable"


class ByteRange(StrictModel):
    """A half-open byte range into UTF-8 encoded text."""

    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def end_is_after_start(self) -> ByteRange:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class SourceLocation(StrictModel):
    source_file: Annotated[str, Field(min_length=1)]
    page: Annotated[int, Field(ge=1)] | None = None
    row: str | None = None
    line_start: Annotated[int, Field(ge=1)] | None = None
    line_end: Annotated[int, Field(ge=1)] | None = None
    source_digest: Digest


class ExpectedCounts(StrictModel):
    numbered_rules: Annotated[int, Field(ge=0)]
    general_rules: Annotated[int, Field(ge=0)]
    approved_words: Annotated[int, Field(ge=0)]
    unapproved_words: Annotated[int, Field(ge=0)]


class StandardManifest(StrictModel):
    format_version: Literal["1"]
    standard_id: Literal["ASD-STE100"]
    issue: Literal[9]
    review_state: ReviewState
    source: SourceLocation
    expected_counts: ExpectedCounts
    published_counts: ExpectedCounts
    count_reconciliation: Annotated[str, Field(min_length=1)]
    file_digests: dict[str, Digest]


class RuleRecord(StrictModel):
    rule_id: RuleId
    requirement: Annotated[str, Field(min_length=1)]
    treatment: RuleTreatment
    review_state: ReviewState
    source: SourceLocation
    notes: str | None = None


class ConformanceRecord(StrictModel):
    rule_id: RuleId
    deterministic_checkers: tuple[str, ...] = ()
    coverage_scope: Literal["full", "partial", "none"]
    release_gate: Literal["blocking", "human_review"]
    reason: Annotated[str, Field(min_length=1)]


class DictionaryMeaning(StrictModel):
    meaning_id: Annotated[str, Field(min_length=1)]
    text: Annotated[str, Field(min_length=1)]
    rule_ids: tuple[RuleId, ...] = ()


class DictionaryEntry(StrictModel):
    entry_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")]
    word: Annotated[str, Field(min_length=1)]
    status: Literal["approved", "unapproved"]
    parts_of_speech: tuple[Annotated[str, Field(min_length=1)], ...]
    approved_meanings: tuple[DictionaryMeaning, ...] = ()
    approved_forms: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    review_state: ReviewState
    source: SourceLocation

    @model_validator(mode="after")
    def has_part_of_speech(self) -> DictionaryEntry:
        if not self.parts_of_speech:
            raise ValueError("dictionary entries require a part of speech")
        return self


class StandardExample(StrictModel):
    example_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")]
    rule_ids: tuple[RuleId, ...]
    text: Annotated[str, Field(min_length=1)]
    label: Literal["positive", "negative", "exception", "boundary"]
    explanation: str | None = None
    review_state: ReviewState
    source: SourceLocation


class ProjectTerm(StrictModel):
    term: Annotated[str, Field(min_length=1)]
    category: Literal["technical_noun", "technical_verb"]
    approved_forms: tuple[Annotated[str, Field(min_length=1)], ...] = ()
    meaning: Annotated[str, Field(min_length=1)]
    source: Annotated[str, Field(min_length=1)]


class ProjectDictionary(StrictModel):
    format_version: Literal["1"]
    terms: tuple[ProjectTerm, ...]


class Finding(StrictModel):
    finding_id: Annotated[str, Field(pattern=r"^finding_[0-9a-f]{16}$")]
    rule_id: RuleId
    kind: FindingKind
    message: Annotated[str, Field(min_length=1)]
    byte_range: ByteRange | None = None
    excerpt: str | None = None
    checker_id: Annotated[str, Field(min_length=1)]


class RuleCoverage(StrictModel):
    rule_id: RuleId
    treatment: RuleTreatment
    status: CoverageStatus
    finding_ids: tuple[str, ...] = ()
    reason: str | None = None


class AnalysisResult(StrictModel):
    standard_id: Literal["ASD-STE100"]
    standard_issue: Literal[9]
    standard_digest: Digest
    official_compliance_claimed: Literal[False] = False
    findings: tuple[Finding, ...]
    coverage: tuple[RuleCoverage, ...]
