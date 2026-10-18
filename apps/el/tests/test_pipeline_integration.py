"""Pipeline against the dev stack (`task up` first): idempotent and incremental."""

import os
import tempfile

import clickhouse_connect
import psycopg
import pytest
from el import pipeline
from el.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def raw_ids(settings: Settings) -> list[int]:
    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_http_port,
        username="default",
        password=os.environ["CLICKHOUSE_DEFAULT_PASSWORD"],
    )
    try:
        rows = client.query("SELECT id FROM raw.submissions ORDER BY id").result_rows
    finally:
        client.close()
    return [row[0] for row in rows]


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
    """Each run gets an empty pipelines dir: state must come from ClickHouse."""
    with tempfile.TemporaryDirectory() as pipelines_dir:
        pipeline.run_once(settings, pipelines_dir)


def test_rerun_is_stable_and_new_rows_arrive(settings: Settings) -> None:
    run_fresh(settings)
    first = raw_ids(settings)
    run_fresh(settings)
    assert raw_ids(settings) == first
    # Inserted already soft-deleted so it never shows up in marts.
    new_id = pg_exec(
        settings,
        "INSERT INTO app.submissions (message, browser_family, os_family, deleted_at)"
        " VALUES ('integration test', 'Other', 'Other', now()) RETURNING id",
    )[0][0]
    run_fresh(settings)
    after = raw_ids(settings)
    assert new_id in after
    assert len(after) == len(set(after)) == len(set(first)) + 1
    run_fresh(settings)
    assert raw_ids(settings) == after
