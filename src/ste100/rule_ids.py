"""Canonical ASD-STE100 Issue 9 rule identifiers."""

from __future__ import annotations

_RULE_COUNTS = {1: 14, 2: 2, 3: 7, 4: 5, 5: 5, 6: 6, 7: 3, 8: 7, 9: 4}
ISSUE9_RULE_IDS = tuple(
    [
        f"{section}.{number}"
        for section, count in _RULE_COUNTS.items()
        for number in range(1, count + 1)
    ]
    + [f"GR-{number}" for number in range(1, 9)]
)
ISSUE9_RULE_ID_SET = frozenset(ISSUE9_RULE_IDS)
