"""Match protected values without accepting them inside modified values."""

from __future__ import annotations

import re
from collections.abc import Sequence


def _value_pattern(value: str, kind: str) -> str:
    escaped = re.escape(value)
    if kind == "url":
        return rf"(?<!\S){escaped}(?=$|\s|[.,;:!?])"
    prefix = r"(?<!\w)" if value[0].isalnum() or value[0] == "_" else ""
    suffix = r"(?!\w)" if value[-1].isalnum() or value[-1] == "_" else ""
    return f"{prefix}{escaped}{suffix}"


def protected_occurrences(text: str, protected_values: Sequence[tuple[str, str]]) -> list[str]:
    """Return longest, non-overlapping protected values in textual order."""

    if not protected_values:
        return []
    kinds_by_value = {value: kind for value, kind in protected_values}
    alternatives = sorted(kinds_by_value, key=lambda value: (-len(value), value))
    named_patterns = [
        f"(?P<value{index}>{_value_pattern(value, kinds_by_value[value])})"
        for index, value in enumerate(alternatives)
    ]
    pattern = re.compile("|".join(named_patterns))
    names = {f"value{index}": value for index, value in enumerate(alternatives)}
    occurrences: list[str] = []
    for match in pattern.finditer(text):
        if match.lastgroup is None:
            raise RuntimeError("protected-value pattern did not identify its match")
        occurrences.append(names[match.lastgroup])
    return occurrences
