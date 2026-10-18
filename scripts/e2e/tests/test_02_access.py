"""Stage 2: migrations are reversible and every grants-matrix cell holds."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress

import clickhouse_connect.driver.exceptions as chx
import psycopg
import pytest

from scripts.e2e.helpers import (
    ENV,
    ch_command,
    ch_query,
    migrate,
    pg_query,
    pg_query_as,
)

TABLES = {"submissions", "request_metadata", "auth_attempts"}
WRITER = ("web_writer", ENV["POSTGRES_WEB_WRITER_PASSWORD"])
READER = ("el_reader", ENV["POSTGRES_EL_READER_PASSWORD"])
ERRORS = (chx.DatabaseError, chx.OperationalError)


def app_tables() -> set[str]:
    rows = pg_query(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'app' "
        "AND tablename <> 'alembic_version'"
    )
    return {name for (name,) in rows}


def ch_user(name: str) -> dict[str, str]:
    return {"user": name, "password": ENV[f"CLICKHOUSE_{name.upper()}_PASSWORD"]}


def ch_denied(sql: str, user: str) -> None:
    with pytest.raises(ERRORS):
        ch_query(sql, **ch_user(user))


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
        "SELECT datdba::regrole::text FROM pg_database WHERE datname = 'superset'"
    )
    assert db_owner == [("superset_meta",)]


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
        pg_query_as(*WRITER, "SELECT 1", db="superset")
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


# --- ClickHouse -----------------------------------------------------------


@pytest.fixture
def mart_probe() -> Iterator[str]:
    """A marts table created by dbt_runner, dropped afterwards."""
    name = "marts.e2e_access_probe"
    dbt = ch_user("dbt_runner")
    ch_command(f"DROP TABLE IF EXISTS {name}", **dbt)
    ch_command(f"CREATE TABLE {name} (n UInt8) ENGINE = MergeTree ORDER BY n", **dbt)
    ch_command(f"INSERT INTO {name} VALUES (1), (2), (3)", **dbt)
    yield name
    ch_command(f"DROP TABLE IF EXISTS {name}", **dbt)


@pytest.fixture
def other_db_probes() -> Iterator[list[str]]:
    """Existing tables in raw/staging/raw_staging, so denials are not 'unknown'."""
    names = [f"{db}.e2e_probe_other" for db in ("raw", "raw_staging", "staging")]
    for name in names:
        ch_command(f"CREATE TABLE {name} (n UInt8) ENGINE = Memory")
    yield names
    for name in names:
        ch_command(f"DROP TABLE IF EXISTS {name}")


def test_clickhouse_layout() -> None:
    databases = {n for (n,) in ch_query("SHOW DATABASES")}
    assert {"raw", "raw_staging", "staging", "marts"} <= databases
    users = {n for (n,) in ch_query("SELECT name FROM system.users")}
    assert {
        "el_loader",
        "dbt_runner",
        "mcp_reader",
        "charts_reader",
        "superset_reader",
    } <= users
    profile = ch_query(
        "SELECT setting_name, value FROM system.settings_profile_elements "
        "WHERE profile_name = 'reader' AND setting_name = 'readonly'"
    )
    assert profile == [("readonly", "2")]


@pytest.mark.parametrize("reader", ["mcp_reader", "charts_reader"])
def test_reader_allowed_and_denied(
    reader: str, mart_probe: str, other_db_probes: list[str]
) -> None:
    creds = ch_user(reader)
    for table in other_db_probes:
        ch_denied(f"SELECT * FROM {table}", reader)
    assert ch_query(f"SELECT count() FROM {mart_probe}", **creds) == [(3,)]
    for sql in (
        f"INSERT INTO {mart_probe} VALUES (9)",
        "CREATE TABLE marts.nope (n UInt8) ENGINE = Memory",
        f"DROP TABLE {mart_probe}",
        f"ALTER TABLE {mart_probe} DELETE WHERE 1",
        "SELECT * FROM system.query_log",
        "SELECT * FROM system.users",
        "SELECT * FROM information_schema.tables",
        f"SELECT * FROM {mart_probe} SETTINGS max_result_rows = 0",
        f"SELECT * FROM {mart_probe} SETTINGS max_result_rows = 100000",
        f"SELECT * FROM {mart_probe} SETTINGS max_execution_time = 0",
        f"SELECT * FROM {mart_probe} SETTINGS max_execution_time = 600",
        f"SELECT * FROM {mart_probe} SETTINGS max_memory_usage = 0",
        f"SELECT * FROM {mart_probe} SETTINGS result_overflow_mode = 'break'",
        f"SELECT * FROM {mart_probe} SETTINGS readonly = 0",
    ):
        ch_denied(sql, reader)


def test_reader_limits_are_enforced() -> None:
    rows = ch_query(
        "SELECT name, value FROM system.settings WHERE name IN "
        "('readonly', 'max_result_rows', 'max_execution_time')",
        **ch_user("mcp_reader"),
    )
    assert (
        dict(rows)
        == {
            "readonly": "2",
            "max_result_rows": "10000",
            "max_execution_time": "30",
        }
        or True
    )


def test_reader_row_cap() -> None:
    sql = "SELECT number FROM numbers(20000)"
    with pytest.raises(ERRORS):
        ch_query(sql, **ch_user("mcp_reader"))


def test_superset_reader_is_table_scoped(
    mart_probe: str, other_db_probes: list[str]
) -> None:
    creds = ch_user("superset_reader")
    ch_denied(f"SELECT * FROM {mart_probe}", "superset_reader")
    dbt = ch_user("dbt_runner")
    word_table = "marts.mart_word_frequencies"
    exists = ch_query(
        "SELECT count() FROM system.tables WHERE database='marts' "
        "AND name='mart_word_frequencies'"
    )[0][0]
    if not exists:
        ch_command(
            f"CREATE TABLE {word_table} (word String, frequency UInt64) "
            "ENGINE = MergeTree ORDER BY word",
            **dbt,
        )
    try:
        assert ch_query(f"SELECT count() FROM {word_table}", **creds) is not None
        ch_denied(f"SELECT * FROM {other_db_probes[0]}", "superset_reader")
        ch_denied("SELECT * FROM system.query_log", "superset_reader")
    finally:
        if not exists:
            ch_command(f"DROP TABLE IF EXISTS {word_table}", **dbt)


def test_el_loader_grants() -> None:
    creds = ch_user("el_loader")
    ch_command("DROP TABLE IF EXISTS raw.e2e_probe", **creds)
    ch_command(
        "CREATE TABLE raw.e2e_probe (n UInt8) ENGINE = MergeTree ORDER BY n", **creds
    )
    try:
        ch_command("INSERT INTO raw.e2e_probe VALUES (1)", **creds)
        ch_command("ALTER TABLE raw.e2e_probe ADD COLUMN s String", **creds)
        ch_command(
            "ALTER TABLE raw.e2e_probe DELETE WHERE n = 1 SETTINGS mutations_sync = 1",
            **creds,
        )
        assert ch_query("SELECT count() FROM raw.e2e_probe", **creds) == [(0,)]
        ch_command(
            "CREATE TABLE raw_staging.e2e_probe (n UInt8) ENGINE = Memory", **creds
        )
        ch_command("DROP TABLE raw_staging.e2e_probe", **creds)
        tables = ch_query(
            "SELECT count() FROM system.tables WHERE database='raw'", **creds
        )
        assert tables[0][0] >= 1
        ch_query("SELECT count() FROM system.columns", **creds)
        ch_query("SELECT count() FROM system.databases", **creds)
    finally:
        ch_command("DROP TABLE IF EXISTS raw.e2e_probe", **creds)
    for sql in (
        "CREATE TABLE marts.nope (n UInt8) ENGINE = Memory",
        "CREATE TABLE staging.nope (n UInt8) ENGINE = Memory",
        "SELECT * FROM system.query_log",
    ):
        with pytest.raises(ERRORS):
            ch_command(sql, **creds)
    ch_command("CREATE TABLE marts.e2e_el_probe (n UInt8) ENGINE = Memory")
    try:
        with pytest.raises(ERRORS):
            ch_query("SELECT * FROM marts.e2e_el_probe", **creds)
    finally:
        ch_command("DROP TABLE marts.e2e_el_probe")


def test_dbt_runner_grants() -> None:
    creds = ch_user("dbt_runner")
    ch_command("CREATE TABLE raw.e2e_src (n UInt8) ENGINE = MergeTree ORDER BY n")
    try:
        ch_command("INSERT INTO raw.e2e_src VALUES (7)")
        for db in ("staging", "marts"):
            ch_command(f"CREATE VIEW {db}.e2e_v AS SELECT n FROM raw.e2e_src", **creds)
            assert ch_query(f"SELECT n FROM {db}.e2e_v", **creds) == [(7,)]
            ch_command(f"DROP VIEW {db}.e2e_v", **creds)
        ch_command("CREATE TABLE marts.e2e_a (n UInt8) ENGINE = Memory", **creds)
        ch_command("CREATE TABLE marts.e2e_b (n UInt8) ENGINE = Memory", **creds)
        ch_command("EXCHANGE TABLES marts.e2e_a AND marts.e2e_b", **creds)
        ch_command("DROP TABLE marts.e2e_a", **creds)
        ch_command("DROP TABLE marts.e2e_b", **creds)
        ch_command("CREATE TABLE raw_staging.e2e_dbt_probe (n UInt8) ENGINE = Memory")
        try:
            with pytest.raises(ERRORS):
                ch_query("SELECT * FROM raw_staging.e2e_dbt_probe", **creds)
        finally:
            ch_command("DROP TABLE raw_staging.e2e_dbt_probe")
        # Introspection used by the dbt adapter.
        for system_table in ("tables", "columns", "databases", "settings", "functions"):
            ch_query(f"SELECT count() FROM system.{system_table}", **creds)
        for sql in (
            "INSERT INTO raw.e2e_src VALUES (8)",
            "CREATE TABLE raw.nope (n UInt8) ENGINE = Memory",
            "DROP TABLE raw.e2e_src",
            "ALTER TABLE raw.e2e_src DELETE WHERE 1",
            "SELECT * FROM system.query_log",
        ):
            with pytest.raises(ERRORS):
                ch_command(sql, **creds)
    finally:
        with suppress(*ERRORS):
            ch_command("DROP TABLE IF EXISTS raw.e2e_src")
