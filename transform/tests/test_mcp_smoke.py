"""Tests for the pure parts of the MCP smoke test: no Docker, no platform."""

import pytest

from scripts.mcp_smoke import (
    ALLOWED_TOOLS,
    EXPECTED_METRICS,
    SmokeResult,
    check,
    contains_number,
    parse_rows,
)


def result(**overrides: object) -> SmokeResult:
    values: dict[str, object] = {
        "tools": sorted(ALLOWED_TOOLS),
        "rows": [{"browser": "Chrome"}],
        "metrics_listing": ", ".join(EXPECTED_METRICS),
        "warehouse_total": 532,
        "metric_answer": "submissions_count\n532",
    }
    return SmokeResult(**{**values, **overrides})  # type: ignore[arg-type]


def test_parse_rows_lowercases_snowflake_column_names() -> None:
    text = 'noise\n[{"BROWSER": "Chrome", "SUBMISSIONS_COUNT": 3}]'
    assert parse_rows(text) == [{"browser": "Chrome", "submissions_count": 3}]


def test_parse_rows_without_json_is_an_error() -> None:
    with pytest.raises(ValueError):
        parse_rows("nothing here")


def test_contains_number_matches_whole_numbers_only() -> None:
    assert contains_number("submissions_count\n532", 532)
    assert not contains_number("5320", 532)
    assert not contains_number("no digits", 532)


def test_check_accepts_a_consistent_result() -> None:
    check(result())


def test_check_skips_the_semantic_layer_when_it_was_not_asked_for() -> None:
    local_only = SmokeResult(tools=sorted(ALLOWED_TOOLS), rows=[{"browser": "Chrome"}])
    check(local_only)


def test_check_rejects_a_missing_tool() -> None:
    with pytest.raises(AssertionError, match="unexpected tools"):
        check(result(tools=["show"]))


def test_check_rejects_a_missing_metric() -> None:
    with pytest.raises(AssertionError, match="mobile_share"):
        check(result(metrics_listing="submissions_count"))


def test_check_rejects_a_metric_that_disagrees_with_the_warehouse() -> None:
    with pytest.raises(AssertionError, match="disagrees"):
        check(result(metric_answer="submissions_count\n10"))
