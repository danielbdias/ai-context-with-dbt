"""Stage 5: dbt v2 builds staging and marts that match the Postgres state.

Runs after stage 4, so one row is soft-deleted and a 7th was added. Expected
values are computed from Postgres (live rows only), not hard-coded.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

import pytest

from scripts.e2e.helpers import ENV, ch_query, pg_query, run_dbt
from scripts.e2e.payloads import EXPECTED_WORD_COUNTS, STOPWORDS_PRESENT

BROWSERS = {"Chrome": "Chrome", "Firefox": "Firefox", "Mobile Safari": "Safari"}
SYSTEMS = {"Mac OS X": "macOS", "Linux": "Linux", "iOS": "iOS"}
LETTERS = re.compile(r"[^\W\d_]+")


def fold(word: str) -> str:
    """Lowercase and strip accents, like the `normalize_token` macro."""
    decomposed = unicodedata.normalize("NFD", word.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def live_rows() -> list[tuple[str, str, str]]:
    """(message, browser_family, os_family) of every non-deleted submission."""
    return pg_query(
        "SELECT message, browser_family, os_family FROM app.submissions"
        " WHERE deleted_at IS NULL"
    )


def live_word_counts() -> Counter[str]:
    """Folded word counts over live messages (stopwords not removed)."""
    return Counter(
        fold(word) for message, _, _ in live_rows() for word in LETTERS.findall(message)
    )


@pytest.fixture(scope="module")
def dbt_build() -> None:
    """Build everything once for this module."""
    result = run_dbt("build")
    assert result.returncode == 0, result.stdout + result.stderr


def test_dbt_build_succeeds(dbt_build: None) -> None:
    """Seeds, models, data tests and unit tests all pass (exit code 0)."""


def test_dbt_docs_generate_succeeds(dbt_build: None) -> None:
    result = run_dbt("docs", "generate")
    assert result.returncode == 0, result.stdout + result.stderr


def test_staging_flags_the_deleted_row(dbt_build: None) -> None:
    total, deleted = ch_query(
        "SELECT count(), countIf(is_deleted) FROM staging.stg_app__submissions"
    )[0]
    assert (total, deleted) == (7, 1)


def test_distributions_match_live_postgres_rows(dbt_build: None) -> None:
    rows = live_rows()
    browsers = Counter(BROWSERS[browser] for _, browser, _ in rows)
    systems = Counter(SYSTEMS[system] for _, _, system in rows)
    browser_sql = (
        "SELECT browser, submissions_count FROM marts.mart_browser_distribution"
    )
    os_sql = "SELECT os, submissions_count FROM marts.mart_os_distribution"
    assert dict(ch_query(browser_sql)) == dict(browsers)
    assert dict(ch_query(os_sql)) == dict(systems)
    assert ch_query("SELECT count() FROM marts.fct_submissions")[0][0] == len(rows)
    assert ch_query(
        "SELECT max(cumulative_submissions) FROM marts.mart_submissions_daily"
    )[0][0] == len(rows)


def test_word_frequencies_match_fixture(dbt_build: None) -> None:
    live = live_word_counts()
    marts = dict(ch_query("SELECT word, frequency FROM marts.mart_word_frequencies"))
    for word in EXPECTED_WORD_COUNTS:
        assert marts[word] == live[word], word
    # The deleted first message held one "cafe" and one "dados".
    assert live["cafe"] == EXPECTED_WORD_COUNTS["cafe"] - 1
    assert live["dados"] == EXPECTED_WORD_COUNTS["dados"] - 1
    assert marts["seventh"] == 1


def test_cafe_and_café_are_merged(dbt_build: None) -> None:
    rows = ch_query(
        "SELECT word, display_word FROM marts.mart_word_frequencies"
        " WHERE word IN ('cafe', 'café')"
    )
    assert [word for word, _ in rows] == ["cafe"]
    assert rows[0][1] in {"cafe", "café"}


def test_no_stopwords_and_no_short_tokens(dbt_build: None) -> None:
    words = {w for (w,) in ch_query("SELECT word FROM marts.mart_word_frequencies")}
    assert words
    assert not words & set(STOPWORDS_PRESENT)
    assert all(len(word) >= 3 for word in words)


@pytest.mark.parametrize("reader", ["mcp_reader", "charts_reader"])
def test_readers_select_the_built_marts(dbt_build: None, reader: str) -> None:
    """Assert 10: readers can SELECT the real marts, not just a probe table."""
    creds = {"user": reader, "password": ENV[f"CLICKHOUSE_{reader.upper()}_PASSWORD"]}
    for table in ("fct_submissions", "mart_browser_distribution"):
        rows = ch_query(f"SELECT count() FROM marts.{table}", **creds)
        assert rows[0][0] > 0, table
