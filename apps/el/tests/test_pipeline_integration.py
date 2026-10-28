"""Pipeline against the dev stack (`task up` first): idempotent and incremental."""

import os
import tempfile

import psycopg
import pytest
import snowflake.connector
from el import pipeline
from el.settings import Settings, snowflake_credentials

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def raw_ids(settings: Settings) -> list[int]:
    credentials = snowflake_credentials(settings)
    conn = snowflake.connector.connect(
        account=credentials["host"],
        user=credentials["username"],
        password=credentials["password"],
        role=credentials["role"],
        warehouse=credentials["warehouse"],
        database=credentials["database"],
    )
    try:
        rows = conn.cursor().execute("SELECT id FROM raw.submissions ORDER BY id")
        return [row[0] for row in rows]
    finally:
        conn.close()


def pg_exec(settings: Settings, sql: str) -> list[tuple]:
    with psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user="postgres",
        password=os.environ["POSTGRES_ADMIN_PASSWORD"],
        dbname=settings.postgres_db,
        autocommit=True,
    ) as conn:
        cur = conn.execute(sql)  # type: ignore[arg-type]
        return cur.fetchall() if cur.description else []


def run_fresh(settings: Settings) -> None:
    """Each run gets an empty pipelines dir: state must come from Snowflake."""
    with tempfile.TemporaryDirectory() as pipelines_dir:
        pipeline.run_once(settings, pipelines_dir)


def insert_deleted_row(settings: Settings) -> int:
    """Insert a row already soft-deleted, so it never shows up in marts."""
    return pg_exec(
        settings,
        "INSERT INTO app.submissions (message, browser_family, os_family, deleted_at)"
        " VALUES ('integration test', 'Other', 'Other', now()) RETURNING id",
    )[0][0]


def test_rerun_is_stable_and_new_rows_arrive(settings: Settings) -> None:
    # At least one source row, so dlt creates raw.submissions on a fresh stack.
    insert_deleted_row(settings)
    run_fresh(settings)
    first = raw_ids(settings)
    run_fresh(settings)
    assert raw_ids(settings) == first
    new_id = insert_deleted_row(settings)
    run_fresh(settings)
    after = raw_ids(settings)
    assert new_id in after
    assert len(after) == len(set(after)) == len(set(first)) + 1
    run_fresh(settings)
    assert raw_ids(settings) == after
