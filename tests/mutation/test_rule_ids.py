_EXPECTED = tuple(
    [
        *(f"1.{number}" for number in range(1, 15)),
        *(f"2.{number}" for number in range(1, 3)),
        *(f"3.{number}" for number in range(1, 8)),
        *(f"4.{number}" for number in range(1, 6)),
        *(f"5.{number}" for number in range(1, 6)),
        *(f"6.{number}" for number in range(1, 7)),
        *(f"7.{number}" for number in range(1, 4)),
        *(f"8.{number}" for number in range(1, 8)),
        *(f"9.{number}" for number in range(1, 5)),
        *(f"GR-{number}" for number in range(1, 9)),
    ]
)


def test_catalog_is_exact() -> None:
    import importlib
    import sys

    sys.modules.pop("ste100.rule_ids", None)
    module = importlib.import_module("ste100.rule_ids")
    assert module.ISSUE9_RULE_IDS == _EXPECTED
    assert module.ISSUE9_RULE_ID_SET == frozenset(_EXPECTED)
