"""Strict contracts for STE100 checks and extracted standard data."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
RuleId = Annotated[str, Field(pattern=r"^(?:[1-9]\d*\.[1-9]\d*|GR-[1-9]\d*)$")]


class StrictModel(BaseModel):
    """Base model that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


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


class StandardManifest(StrictModel):
    format_version: Literal["1"]
    standard_id: Literal["ASD-STE100"]
    issue: Literal[9]
    source: SourceLocation
    file_digests: dict[str, Digest]


class RuleRecord(StrictModel):
    rule_id: RuleId
    requirement: Annotated[str, Field(min_length=1)]
    source: SourceLocation


class DictionaryEntry(StrictModel):
    entry_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")]
    word: Annotated[str, Field(min_length=1)]
    qualifier: str | None = None
    status: Literal["approved", "unapproved"]
    parts_of_speech: tuple[Annotated[str, Field(min_length=1)], ...]
    approved_forms: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    source: SourceLocation

    @model_validator(mode="after")
    def has_part_of_speech(self) -> DictionaryEntry:
        if not self.parts_of_speech:
            raise ValueError("dictionary entries require a part of speech")
        return self


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
    rule_ids: Annotated[tuple[RuleId, ...], Field(min_length=1)]
    message: Annotated[str, Field(min_length=1)]
    byte_range: ByteRange
    excerpt: str


class AnalysisResult(StrictModel):
    standard_id: Literal["ASD-STE100"]
    standard_issue: Literal[9]
    standard_digest: Digest
    passed: bool
    findings: tuple[Finding, ...]

    @model_validator(mode="after")
    def passed_matches_findings(self) -> AnalysisResult:
        if self.passed is bool(self.findings):
            raise ValueError("passed must be true exactly when findings is empty")
        return self
