"""Untrusted rewrite-candidate pipeline with protected-content gates."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from ste100.checker import analyze
from ste100.contracts import Rewriter
from ste100.models import AnalysisResult, ByteRange, FindingKind, ProjectDictionary
from ste100.protection import ProtectedContentError, ProtectedDocument, protect_text
from ste100.standard import StandardPack


@dataclass(frozen=True, slots=True)
class RewriteOutcome:
    model_id: str
    status: Literal["review_required", "rejected"]
    candidate: str | None
    source_analysis: AnalysisResult
    candidate_analysis: AnalysisResult | None
    protected_document: ProtectedDocument
    deterministic_gate_passed: bool
    rejection_reason: str | None = None
    official_compliance_claimed: bool = False


def _deterministic_violations(
    result: AnalysisResult,
) -> Counter[tuple[str, str | None]]:
    return Counter(
        (finding.rule_id, finding.excerpt)
        for finding in result.findings
        if finding.kind is FindingKind.VIOLATION and finding.checker_id is not None
    )


def rewrite_candidate(
    text: str,
    *,
    rewriter: Rewriter,
    standard: StandardPack | None = None,
    project_dictionary: ProjectDictionary | None = None,
    caller_ranges: tuple[ByteRange, ...] = (),
    use_detector_hints: bool = False,
) -> RewriteOutcome:
    """Create and recheck a candidate; this function never certifies STE compliance."""

    source_analysis = analyze(
        text,
        standard=standard,
        project_dictionary=project_dictionary,
    )
    protected = protect_text(
        text,
        project_dictionary=project_dictionary,
        caller_ranges=caller_ranges,
    )
    hints = source_analysis.findings if use_detector_hints else ()
    masked_candidate = rewriter.rewrite(protected.masked_text, hints)
    try:
        candidate = protected.restore(masked_candidate)
    except ProtectedContentError as error:
        return RewriteOutcome(
            model_id=rewriter.model_id,
            status="rejected",
            candidate=None,
            source_analysis=source_analysis,
            candidate_analysis=None,
            protected_document=protected,
            deterministic_gate_passed=False,
            rejection_reason=str(error),
        )
    candidate_analysis = analyze(
        candidate,
        standard=standard,
        project_dictionary=project_dictionary,
    )
    source_violations = _deterministic_violations(source_analysis)
    candidate_violations = _deterministic_violations(candidate_analysis)
    gate_passed = candidate_violations <= source_violations
    return RewriteOutcome(
        model_id=rewriter.model_id,
        status="review_required" if gate_passed else "rejected",
        candidate=candidate if gate_passed else None,
        source_analysis=source_analysis,
        candidate_analysis=candidate_analysis,
        protected_document=protected,
        deterministic_gate_passed=gate_passed,
        rejection_reason=None if gate_passed else "candidate introduced a deterministic violation",
    )
