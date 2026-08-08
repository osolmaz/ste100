"""Validated data contracts shared by the checker and learned components."""

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
    LEARNED = "learned"
    HUMAN_REVIEW = "human_review"
    NOT_CHECKED = "not_checked"


class FindingKind(StrEnum):
    VIOLATION = "violation"
    PROBABLE_VIOLATION = "probable_violation"
    HUMAN_REVIEW = "human_review"
    NOT_CHECKED = "not_checked"


class CoverageStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    PROBABLE_VIOLATION = "probable_violation"
    HUMAN_REVIEW = "human_review"
    NOT_CHECKED = "not_checked"
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
    source_file: str
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
    learned_role: Literal["detector", "rewriter"] | None = None
    coverage_scope: Literal["full", "partial", "none"]
    release_gate: Literal["blocking", "report_only", "human_review"]
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


class DictionaryCandidate(StrictModel):
    candidate_id: Annotated[str, Field(pattern=r"^candidate_[0-9a-f]{16}$")]
    displayed_word: Annotated[str, Field(min_length=1)]
    normalized_word: Annotated[str, Field(min_length=1)]
    status: Literal["approved", "unapproved"]
    part_of_speech: Annotated[str, Field(min_length=1)]
    raw_line: Annotated[str, Field(min_length=1)]
    review_state: Literal[ReviewState.DRAFT] = ReviewState.DRAFT
    source: SourceLocation


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
    checker_id: str | None = None
    model_id: str | None = None
    score: Annotated[float, Field(ge=0, le=1)] | None = None


class RuleCoverage(StrictModel):
    rule_id: RuleId
    treatment: RuleTreatment
    status: CoverageStatus
    finding_ids: tuple[str, ...] = ()
    reason: str | None = None


class AnalysisResult(StrictModel):
    standard_id: str
    standard_issue: int
    official_compliance_claimed: Literal[False] = False
    findings: tuple[Finding, ...]
    coverage: tuple[RuleCoverage, ...]


class ProtectedSpan(StrictModel):
    span_id: Annotated[str, Field(pattern=r"^span_[0-9a-f]{16}$")]
    kind: Literal[
        "project_term",
        "number",
        "unit",
        "identifier",
        "url",
        "code",
        "caller",
    ]
    byte_range: ByteRange
    text_digest: Digest


class SplitMembership(StrictModel):
    split: Literal["train", "validation", "test", "sealed_test"]
    group_id: Annotated[str, Field(min_length=1)]
    time_bucket: str | None = None
    model_family: str | None = None


class ViolationAnnotation(StrictModel):
    rule_id: RuleId
    label: Literal["violation", "no_violation", "exception", "uncertain"]
    byte_range: ByteRange | None = None
    annotator: Annotated[str, Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None


class DatasetRecord(StrictModel):
    record_id: Annotated[str, Field(pattern=r"^record_[0-9a-f]{16}$")]
    source_kind: Literal[
        "standard_example",
        "technical_document",
        "conversation_revision",
        "synthetic",
    ]
    source_id: Annotated[str, Field(min_length=1)]
    source_digest: Digest
    parent_record_ids: tuple[Annotated[str, Field(pattern=r"^record_[0-9a-f]{16}$")], ...] = ()
    text: Annotated[str, Field(min_length=1)]
    rule_ids: tuple[RuleId, ...] = ()
    annotations: tuple[ViolationAnnotation, ...] = ()
    protected_spans: tuple[ProtectedSpan, ...] = ()
    split: SplitMembership
    annotation_state: Literal["weak", "reviewed", "adjudicated"]
    observed_outcome: Literal[
        "revision_requested",
        "continued_without_revision",
        "conversation_ended",
        "explicit_approval",
        "not_applicable",
    ] = "not_applicable"
    target_text: str | None = None
    inferred_approval: Literal[False] = False

    @model_validator(mode="after")
    def conversation_outcome_is_explicit(self) -> DatasetRecord:
        if (
            self.source_kind == "conversation_revision"
            and self.observed_outcome == "not_applicable"
        ):
            raise ValueError("conversation revisions require an observed outcome")
        if (
            self.source_kind != "conversation_revision"
            and self.observed_outcome != "not_applicable"
        ):
            raise ValueError("observed outcomes apply only to conversation revisions")
        return self


class ModelManifest(StrictModel):
    format_version: Literal["1"]
    model_id: Annotated[str, Field(min_length=1)]
    role: Literal["detector", "rewriter"]
    release: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    artifact_digest: Digest
    evaluation_digest: Digest
    standard_issue: Literal[9]
    base_model_id: Annotated[str, Field(min_length=1)]
    base_model_revision: Annotated[str, Field(min_length=1)]
    pretraining_contamination: Literal["known_absent", "known_present", "unknown"]
    dataset_digests: tuple[Digest, ...]
    thresholds: dict[str, Annotated[float, Field(ge=0, le=1)]]
    protected_content_gate: bool
    span_release_gate: Literal["report_only", "blocking"]
    detector_hints_used: bool
    selection_authority: Literal["maintainer"] = "maintainer"
    official_compliance_claimed: Literal[False] = False

    @model_validator(mode="after")
    def release_safety_fields_match_role(self) -> ModelManifest:
        if self.role == "rewriter" and not self.protected_content_gate:
            raise ValueError("rewriter releases require the protected-content gate")
        if self.role == "rewriter" and self.span_release_gate != "report_only":
            raise ValueError("span gating applies only to detector releases")
        if not self.dataset_digests:
            raise ValueError("model releases require at least one dataset digest")
        return self
