"""Stage 4: dlt copies only `submissions`, idempotently, soft deletes included."""

from __future__ import annotations

import pytest

from scripts.e2e.helpers import ENV, pg_query, run_el, sf_query
from scripts.e2e.payloads import SAMPLES
from scripts.seed import make_client, submit

AUX_TABLES = ("REQUEST_METADATA", "AUTH_ATTEMPTS")

pytestmark = pytest.mark.usefixtures("e2e_database")


def pg_submission_count() -> int:
    return pg_query("SELECT count(*) FROM app.submissions")[0][0]


def raw_counts() -> tuple[int, int]:
    """(rows, distinct ids) in the raw table."""
    return sf_query("SELECT count(*), count(DISTINCT id) FROM RAW.SUBMISSIONS")[0]


def el_ok() -> None:
    result = run_el()
    assert result.returncode == 0, result.stdout + result.stderr


def test_el_is_idempotent() -> None:
    expected = pg_submission_count()
    assert expected == 6
    for _ in range(2):
        el_ok()
        assert raw_counts() == (expected, expected)


def test_soft_delete_and_new_row_propagate() -> None:
    victim = pg_query("SELECT min(id) FROM app.submissions")[0][0]
    pg_query(
        "UPDATE app.submissions SET deleted_at = now() WHERE id = %s", params=(victim,)
    )
    with make_client(f"http://127.0.0.1:{ENV['WEB_PORT']}", SAMPLES[0]) as client:
        assert (
            submit(client, ENV["APP_PASSWORD"], "a seventh message").status_code == 303
        )
    el_ok()
    assert pg_submission_count() == 7
    assert raw_counts() == (7, 7)
    latest = sf_query(
        "SELECT id, max_by(deleted_at, updated_at) FROM RAW.SUBMISSIONS"
        " GROUP BY id ORDER BY id"
    )
    assert len(latest) == 7
    deleted = [row_id for row_id, deleted_at in latest if deleted_at is not None]
    assert deleted == [victim]
    el_ok()
    assert raw_counts() == (7, 7)


def test_auxiliary_tables_never_reach_snowflake() -> None:
    names = {
        name
        for (name,) in sf_query(
            "SELECT table_name FROM INFORMATION_SCHEMA.TABLES"
            " WHERE table_schema = 'RAW'"
        )
    }
    assert not names & set(AUX_TABLES)
    assert "SUBMISSIONS" in names


def test_el_fails_when_snowflake_is_unreachable() -> None:
    result = run_el(
        {"SNOWFLAKE_ACCOUNT": "unreachable-e2e.invalid", "EL_MAX_ATTEMPTS": "1"}
    )
    assert result.returncode != 0
