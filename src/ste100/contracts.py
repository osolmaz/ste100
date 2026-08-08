"""Stable interfaces for separately released learned components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ste100.models import ByteRange, Finding


@dataclass(frozen=True, slots=True)
class DetectorPrediction:
    rule_id: str
    score: float
    message: str
    byte_range: ByteRange | None = None


@runtime_checkable
class Detector(Protocol):
    @property
    def model_id(self) -> str: ...

    def detect(self, text: str) -> tuple[DetectorPrediction, ...]:
        """Return probable violations; absence of predictions is not certification."""


@runtime_checkable
class Rewriter(Protocol):
    @property
    def model_id(self) -> str: ...

    def rewrite(self, masked_text: str, findings: tuple[Finding, ...]) -> str:
        """Return a candidate containing all protected sentinels unchanged and in order."""


@dataclass(frozen=True, slots=True)
class StaticDetector:
    """A deterministic detector double for integration tests and offline clients."""

    model_id: str
    predictions: tuple[DetectorPrediction, ...]

    def detect(self, text: str) -> tuple[DetectorPrediction, ...]:
        del text
        return self.predictions


@dataclass(frozen=True, slots=True)
class StaticRewriter:
    """A deterministic rewriter double for integration tests and offline clients."""

    model_id: str
    candidate: str

    def rewrite(self, masked_text: str, findings: tuple[Finding, ...]) -> str:
        del masked_text, findings
        return self.candidate
