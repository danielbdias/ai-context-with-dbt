"""Stage 2: migrations are reversible and every grants-matrix cell holds."""

from __future__ import annotations

import time
from collections.abc import Iterator

import psycopg
import pytest

from scripts.e2e.helpers import (
    DENIED,
    ENV,
    migrate,
    pg_query,
    pg_query_as,
    sf_connect,
    sf_query,
)

TABLES = {"submissions", "request_metadata", "auth_attempts"}
WRITER = ("web_writer", ENV["POSTGRES_WEB_WRITER_PASSWORD"])
READER = ("el_reader", ENV["POSTGRES_EL_READER_PASSWORD"])
SCHEMAS = {"RAW", "RAW_STAGING", "STAGING", "MARTS"}
SERVICE_USERS = {"EL_LOADER", "DBT_RUNNER", "MCP_READER", "CHARTS_READER"}
ACCOUNT_USAGE = "SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY LIMIT 1"
READERS = ["mcp_reader", "charts_reader"]


def app_tables() -> set[str]:
    rows = pg_query(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'app' "
        "AND tablename <> 'alembic_version'"
    )
    return {name for (name,) in rows}


def denied(sql: str, user: str) -> None:
    """The statement must fail for `user` (not authorized or no privilege)."""
    with pytest.raises(DENIED):
        sf_query(sql, user)


# --- Postgres -------------------------------------------------------------


def test_migrations_roundtrip() -> None:
    migrate("head")
    assert app_tables() == TABLES
    migrate("base", direction="downgrade")
    assert app_tables() == set()
    assert pg_query("SELECT 1 FROM pg_proc WHERE proname = 'set_updated_at'") == []
    migrate("head")
    assert app_tables() == TABLES


def test_postgres_objects_exist() -> None:
    indexes = {
        name
        for (name,) in pg_query(
            "SELECT indexname FROM pg_indexes WHERE schemaname='app'"
        )
    }
    assert {"submissions_updated_at_idx", "auth_attempts_ip_time_idx"} <= indexes
    triggers = pg_query(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'app.submissions'::regclass "
        "AND NOT tgisinternal"
    )
    assert triggers == [("submissions_set_updated_at",)]
    owner = pg_query(
        "SELECT nspowner::regrole::text FROM pg_namespace WHERE nspname = 'app'"
    )
    assert owner == [("app_owner",)]
    db_owner = pg_query(
        "SELECT datdba::regrole::text FROM pg_database WHERE datname = 'app'"
    )
    assert db_owner == [("postgres",)]


def test_updated_at_trigger_and_check() -> None:
    pg_query(
        "INSERT INTO app.submissions (message, browser_family, os_family, updated_at) "
        "VALUES ('trigger probe', 'Chrome', 'macOS', '2000-01-01')"
    )
    pg_query(
        "UPDATE app.submissions SET deleted_at = now() WHERE message='trigger probe'"
    )
    rows = pg_query(
        "SELECT updated_at > '2000-01-02' FROM app.submissions "
        "WHERE message = 'trigger probe'"
    )
    assert rows == [(True,)]
    with pytest.raises(psycopg.errors.CheckViolation):
        pg_query(
            "INSERT INTO app.submissions (message, browser_family, os_family) "
            "VALUES ('   ', 'Chrome', 'macOS')"
        )
    pg_query("DELETE FROM app.submissions WHERE message = 'trigger probe'")


def test_web_writer_privileges() -> None:
    rows = pg_query_as(
        *WRITER,
        "INSERT INTO app.submissions (message, browser_family, os_family) "
        "VALUES ('writer probe', 'Chrome', 'macOS') RETURNING id",
    )
    submission_id = rows[0][0]
    pg_query_as(
        *WRITER,
        "INSERT INTO app.request_metadata (submission_id, user_agent_raw, ip_hash) "
        f"VALUES ({submission_id}, 'ua', repeat('a', 64))",
    )
    pg_query_as(
        *WRITER,
        "INSERT INTO app.auth_attempts (ip_hash, success, reason, submission_id) "
        f"VALUES (repeat('a', 64), true, 'ok', {submission_id})",
    )
    assert pg_query_as(*WRITER, "SELECT count(*) FROM app.auth_attempts")[0][0] >= 1
    denied = [
        "SELECT * FROM app.request_metadata",
        "SELECT message FROM app.submissions",
        "UPDATE app.submissions SET message = 'x'",
        "DELETE FROM app.auth_attempts",
        "CREATE TABLE app.nope (id int)",
    ]
    for sql in denied:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            pg_query_as(*WRITER, sql)
    with pytest.raises(psycopg.OperationalError):
        pg_query_as(*WRITER, "SELECT 1", db="postgres")
    pg_query("DELETE FROM app.submissions WHERE message = 'writer probe'")


def test_el_reader_privileges() -> None:
    assert pg_query_as(*READER, "SELECT count(*) FROM app.submissions")
    for sql in (
        "SELECT * FROM app.request_metadata",
        "SELECT * FROM app.auth_attempts",
        "INSERT INTO app.submissions (message, browser_family, os_family) "
        "VALUES ('x', 'a', 'b')",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            pg_query_as(*READER, sql)


# --- Snowflake ------------------------------------------------------------
# Each test runs in the per-run database. Snowflake has no `readonly` flag, row
# cap or memory cap, so readers are read-only through grants alone, and bounded
# by a statement timeout and a resource monitor (infra/snowflake/setup.sql).


@pytest.fixture
def mart_probe(e2e_database: str) -> Iterator[str]:
    """A MARTS table created by dbt_runner, dropped afterwards."""
    name = "MARTS.E2E_ACCESS_PROBE"
    sf_query(f"CREATE OR REPLACE TABLE {name} (n NUMBER)", "dbt_runner")
    sf_query(f"INSERT INTO {name} VALUES (1), (2), (3)", "dbt_runner")
    yield name
    sf_query(f"DROP TABLE IF EXISTS {name}", "dbt_runner")


@pytest.fixture
def other_schema_probes(e2e_database: str) -> Iterator[list[str]]:
    """Existing tables in RAW, RAW_STAGING and STAGING, so denials are real."""
    owners = {
        "RAW.E2E_PROBE_OTHER": "el_loader",
        "RAW_STAGING.E2E_PROBE_OTHER": "el_loader",
        "STAGING.E2E_PROBE_OTHER": "dbt_runner",
    }
    for name, owner in owners.items():
        sf_query(f"CREATE OR REPLACE TABLE {name} (n NUMBER)", owner)
    yield list(owners)
    for name, owner in owners.items():
        sf_query(f"DROP TABLE IF EXISTS {name}", owner)


def test_snowflake_layout(e2e_database: str) -> None:
    schemas = {
        name
        for (name,) in sf_query(
            "SELECT schema_name FROM INFORMATION_SCHEMA.SCHEMATA", "admin"
        )
    }
    assert schemas >= SCHEMAS
    users = {row[0] for row in sf_query("SHOW USERS", "admin")}
    assert users >= SERVICE_USERS
    assert "SUPERSET_READER" not in users


@pytest.mark.parametrize("reader", READERS)
def test_reader_allowed_and_denied(
    reader: str, mart_probe: str, other_schema_probes: list[str]
) -> None:
    for table in other_schema_probes:
        denied(f"SELECT * FROM {table}", reader)
    assert sf_query(f"SELECT count(*) FROM {mart_probe}", reader) == [(3,)]
    for sql in (
        f"INSERT INTO {mart_probe} VALUES (9)",
        "CREATE TABLE MARTS.E2E_NOPE (n NUMBER)",
        f"DROP TABLE {mart_probe}",
        f"ALTER TABLE {mart_probe} ADD COLUMN x NUMBER",
        f"DELETE FROM {mart_probe}",
        f"TRUNCATE TABLE {mart_probe}",
        "CREATE SCHEMA E2E_NOPE",
        ACCOUNT_USAGE,
    ):
        denied(sql, reader)


@pytest.mark.parametrize("reader", READERS)
def test_reader_sees_only_marts_in_the_catalog(
    reader: str, mart_probe: str, other_schema_probes: list[str]
) -> None:
    rows = sf_query(
        "SELECT DISTINCT table_schema FROM INFORMATION_SCHEMA.TABLES"
        " WHERE table_schema IN ('RAW', 'RAW_STAGING', 'STAGING', 'MARTS')",
        reader,
    )
    assert rows == [("MARTS",)]


@pytest.mark.parametrize("reader", READERS)
def test_reader_survives_a_dbt_rebuild(reader: str, mart_probe: str) -> None:
    """dbt rebuilds tables with CREATE OR REPLACE, which drops grants on the old
    object. FUTURE grants must give the new one back to the readers."""
    sf_query(f"CREATE OR REPLACE TABLE {mart_probe} (n NUMBER)", "dbt_runner")
    assert sf_query(f"SELECT count(*) FROM {mart_probe}", reader) == [(0,)]


def test_reader_timeout_is_configured_on_user_and_warehouse(e2e_database: str) -> None:
    for scope in ("USER MCP_READER", "USER CHARTS_READER", "WAREHOUSE AICTX_READ_WH"):
        rows = sf_query(
            f"SHOW PARAMETERS LIKE 'STATEMENT_TIMEOUT_IN_SECONDS' IN {scope}", "admin"
        )
        assert [row[1] for row in rows] == ["30"], scope


def test_reader_cannot_raise_its_own_timeout(e2e_database: str) -> None:
    """A session may ask for 600 s, but the user and warehouse cap of 30 s wins."""
    connection = sf_connect("mcp_reader")
    try:
        cursor = connection.cursor()
        cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 600")
        started = time.monotonic()
        with pytest.raises(DENIED, match="timeout of 30"):
            cursor.execute(
                "SELECT count(*) FROM"
                " (SELECT seq4() FROM TABLE(GENERATOR(TIMELIMIT => 45)))"
            )
        assert time.monotonic() - started < 40
    finally:
        connection.close()


def test_el_loader_grants(mart_probe: str, other_schema_probes: list[str]) -> None:
    loader = "el_loader"
    raw, staging = "RAW.E2E_PROBE", "RAW_STAGING.E2E_PROBE"
    for name in (raw, staging):
        sf_query(f"CREATE OR REPLACE TABLE {name} (n NUMBER)", loader)
    try:
        sf_query(f"INSERT INTO {raw} VALUES (1)", loader)
        sf_query(f"ALTER TABLE {raw} ADD COLUMN s VARCHAR", loader)
        sf_query(f"DELETE FROM {raw} WHERE n = 1", loader)
        assert sf_query(f"SELECT count(*) FROM {raw}", loader) == [(0,)]
    finally:
        for name in (raw, staging):
            sf_query(f"DROP TABLE IF EXISTS {name}", loader)
    for sql in (
        "CREATE TABLE MARTS.E2E_NOPE (n NUMBER)",
        "CREATE TABLE STAGING.E2E_NOPE (n NUMBER)",
        "CREATE SCHEMA E2E_NOPE",
        ACCOUNT_USAGE,
    ):
        denied(sql, loader)
    # It cannot read what dbt builds.
    denied(f"SELECT * FROM {mart_probe}", loader)
    denied("SELECT * FROM STAGING.E2E_PROBE_OTHER", loader)


def test_dbt_runner_grants(e2e_database: str, other_schema_probes: list[str]) -> None:
    runner, src = "dbt_runner", "RAW.E2E_SRC"
    sf_query(f"CREATE OR REPLACE TABLE {src} (n NUMBER)", "el_loader")
    try:
        sf_query(f"INSERT INTO {src} VALUES (7)", "el_loader")
        for schema in ("STAGING", "MARTS"):
            view = f"{schema}.E2E_V"
            sf_query(f"CREATE OR REPLACE VIEW {view} AS SELECT n FROM {src}", runner)
            assert sf_query(f"SELECT n FROM {view}", runner) == [(7,)]
            sf_query(f"DROP VIEW {view}", runner)
        sf_query("CREATE OR REPLACE TABLE MARTS.E2E_A (n NUMBER)", runner)
        sf_query("CREATE OR REPLACE TABLE MARTS.E2E_B (n NUMBER)", runner)
        sf_query("ALTER TABLE MARTS.E2E_A SWAP WITH MARTS.E2E_B", runner)
        sf_query("DROP TABLE MARTS.E2E_A", runner)
        sf_query("DROP TABLE MARTS.E2E_B", runner)
        for sql in (
            f"INSERT INTO {src} VALUES (8)",
            "CREATE TABLE RAW.E2E_NOPE (n NUMBER)",
            f"DROP TABLE {src}",
            f"ALTER TABLE {src} ADD COLUMN y NUMBER",
            "CREATE SCHEMA E2E_NOPE",
            "SELECT * FROM RAW_STAGING.E2E_PROBE_OTHER",
            ACCOUNT_USAGE,
        ):
            denied(sql, runner)
    finally:
        sf_query(f"DROP TABLE IF EXISTS {src}", "el_loader")
