"""Stage 5: dbt v2 builds staging and marts that match the Postgres state.

Runs after stage 4, so one row is soft-deleted and a 7th was added. Expected
values are computed from Postgres (live rows only), not hard-coded.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

import pytest

from scripts.e2e.helpers import pg_query, run_dbt, sf_query
from scripts.e2e.payloads import EXPECTED_WORD_COUNTS, STOPWORDS_PRESENT

pytestmark = pytest.mark.usefixtures("e2e_database")

BROWSERS = {"Chrome": "Chrome", "Firefox": "Firefox", "Mobile Safari": "Safari"}
SYSTEMS = {"Mac OS X": "macOS", "Linux": "Linux", "iOS": "iOS"}
LETTERS = re.compile(r"[^\W\d_]+")


def fold(word: str) -> str:
    """Lowercase and strip accents, like the `normalize_token` macro.

    The macro uses a translate() table for Latin letters. For the fixture words
    that gives the same result as stripping Unicode combining marks.
    """
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
    total, deleted = sf_query(
        "SELECT count(*), count_if(is_deleted) FROM STAGING.STG_APP__SUBMISSIONS"
    )[0]
    assert (total, deleted) == (7, 1)


def test_staging_ignores_an_older_deleted_duplicate(dbt_build: None) -> None:
    """Regression: a stale deleted version of a live row must not win the dedup.

    On ClickHouse, argMax skipped NULLs and the stale row won. Snowflake's max_by
    keeps a NULL winner, so this pins that property. Staging is a view, so a raw
    row inserted here shows up without a rebuild.
    """
    live_id = sf_query(
        "SELECT max(submission_id) FROM STAGING.STG_APP__SUBMISSIONS"
        " WHERE NOT is_deleted"
    )[0][0]
    stale = "DATEADD(day, -1, updated_at)"
    sf_query(
        "INSERT INTO RAW.SUBMISSIONS (id, message, browser_family, os_family,"
        " created_at, updated_at, deleted_at, _dlt_load_id, _dlt_id)"
        f" SELECT id, message, browser_family, os_family, created_at, {stale},"
        f" {stale}, _dlt_load_id, 'e2e-stale'"
        f" FROM RAW.SUBMISSIONS WHERE id = {live_id}",
        "el_loader",
    )
    try:
        rows = sf_query(
            "SELECT is_deleted FROM STAGING.STG_APP__SUBMISSIONS"
            f" WHERE submission_id = {live_id}"
        )
        assert rows == [(False,)]
    finally:
        sf_query("DELETE FROM RAW.SUBMISSIONS WHERE _dlt_id = 'e2e-stale'", "el_loader")
    assert sf_query("SELECT count(*) FROM RAW.SUBMISSIONS")[0][0] == 7


def test_distributions_match_live_postgres_rows(dbt_build: None) -> None:
    rows = live_rows()
    browsers = Counter(BROWSERS[browser] for _, browser, _ in rows)
    systems = Counter(SYSTEMS[system] for _, _, system in rows)
    browser_sql = (
        "SELECT browser, submissions_count FROM MARTS.MART_BROWSER_DISTRIBUTION"
    )
    os_sql = "SELECT os, submissions_count FROM MARTS.MART_OS_DISTRIBUTION"
    assert dict(sf_query(browser_sql)) == dict(browsers)
    assert dict(sf_query(os_sql)) == dict(systems)
    assert sf_query("SELECT count(*) FROM MARTS.FCT_SUBMISSIONS")[0][0] == len(rows)
    assert sf_query(
        "SELECT max(cumulative_submissions) FROM MARTS.MART_SUBMISSIONS_DAILY"
    )[0][0] == len(rows)


def test_word_frequencies_match_fixture(dbt_build: None) -> None:
    live = live_word_counts()
    marts = dict(sf_query("SELECT word, frequency FROM MARTS.MART_WORD_FREQUENCIES"))
    for word in EXPECTED_WORD_COUNTS:
        assert marts[word] == live[word], word
    # The deleted first message held one "cafe" and one "dados".
    assert live["cafe"] == EXPECTED_WORD_COUNTS["cafe"] - 1
    assert live["dados"] == EXPECTED_WORD_COUNTS["dados"] - 1
    assert marts["seventh"] == 1


def test_cafe_and_café_are_merged(dbt_build: None) -> None:
    rows = sf_query(
        "SELECT word, display_word FROM MARTS.MART_WORD_FREQUENCIES"
        " WHERE word IN ('cafe', 'café')"
    )
    assert [word for word, _ in rows] == ["cafe"]
    assert rows[0][1] in {"cafe", "café"}


def test_no_stopwords_and_no_short_tokens(dbt_build: None) -> None:
    words = {w for (w,) in sf_query("SELECT word FROM MARTS.MART_WORD_FREQUENCIES")}
    assert words
    assert not words & set(STOPWORDS_PRESENT)
    assert all(len(word) >= 3 for word in words)


@pytest.mark.parametrize("reader", ["mcp_reader", "charts_reader"])
def test_readers_select_the_built_marts(dbt_build: None, reader: str) -> None:
    """Assert 10: readers can SELECT the real marts, not just a probe table."""
    for table in ("FCT_SUBMISSIONS", "MART_BROWSER_DISTRIBUTION"):
        rows = sf_query(f"SELECT count(*) FROM MARTS.{table}", reader)
        assert rows[0][0] > 0, table
