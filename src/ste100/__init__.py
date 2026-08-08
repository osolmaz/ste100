"""Source-backed ASD-STE100 Issue 9 checks."""

from ste100.checker import analyze
from ste100.document import parse_document
from ste100.models import AnalysisResult

__all__ = ["AnalysisResult", "analyze", "parse_document"]
__version__ = "0.2.0"
