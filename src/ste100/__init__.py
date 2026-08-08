"""Deterministic STE100 analysis and learned-component contracts."""

from ste100.checker import analyze
from ste100.document import parse_document
from ste100.models import AnalysisResult

__all__ = ["AnalysisResult", "analyze", "parse_document"]
__version__ = "0.1.0"
