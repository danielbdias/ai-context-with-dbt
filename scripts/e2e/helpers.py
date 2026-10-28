"""Small typed helpers shared by e2e stages: Postgres, Snowflake, compose, HTTP."""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import httpx
import psycopg
import snowflake.connector
from snowflake.connector.errors import ProgrammingError

E2E_DIR = Path(__file__).parent
REPO_ROOT = E2E_DIR.parent.parent
ENV_FILE = E2E_DIR / "e2e.env"
PROJECT = "aictx-e2e"
# Every run gets its own Snowflake database, so it never touches the dev AICTX.
# Set E2E_DATABASE to reuse one (for example after E2E_KEEP=1).
E2E_DATABASE = os.environ.get("E2E_DATABASE") or (
    f"AICTX_E2E_{uuid.uuid4().hex[:8].upper()}"
)
DENIED = ProgrammingError


class SnowflakeUser(NamedTuple):
    """How to log in as one demo service user (see infra/snowflake/setup.sql)."""

    user: str
    role: str
    warehouse: str
    password_variable: str


SNOWFLAKE_USERS = {
    "el_loader": SnowflakeUser(
        "EL_LOADER", "AICTX_EL_LOADER", "AICTX_LOAD_WH", "SNOWFLAKE_EL_LOADER_PASSWORD"
    ),
    "dbt_runner": SnowflakeUser(
        "DBT_RUNNER",
        "AICTX_DBT_RUNNER",
        "AICTX_TRANSFORM_WH",
        "SNOWFLAKE_DBT_RUNNER_PASSWORD",
    ),
    "mcp_reader": SnowflakeUser(
        "MCP_READER",
        "AICTX_MCP_READER",
        "AICTX_READ_WH",
        "SNOWFLAKE_MCP_READER_PASSWORD",
    ),
    "charts_reader": SnowflakeUser(
        "CHARTS_READER",
        "AICTX_CHARTS_READER",
        "AICTX_READ_WH",
        "SNOWFLAKE_CHARTS_READER_PASSWORD",
    ),
}


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse a simple KEY=VALUE env file, ignoring blanks and comments."""
    pairs = (
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    return {key.strip(): value.strip() for key, value in pairs}


ENV = load_env()


def process_env() -> dict[str, str]:
    """Environment for child processes: e2e values win, and the e2e database."""
    return {**os.environ, **ENV, "SNOWFLAKE_DATABASE": E2E_DATABASE}


def pg_query(
    sql: str, db: str = "app", params: Sequence[Any] | None = None
) -> list[tuple[Any, ...]]:
    """Run a query on the e2e Postgres as admin and return all rows."""
    with psycopg.connect(
        host="127.0.0.1",
        port=int(ENV["POSTGRES_PORT"]),
        user="postgres",
        password=ENV["POSTGRES_ADMIN_PASSWORD"],
        dbname=db,
        autocommit=True,
    ) as conn:
        cur = conn.execute(sql, params)  # type: ignore[arg-type]
        return cur.fetchall() if cur.description else []


def sf_connect(user: str) -> snowflake.connector.SnowflakeConnection:
    """Connect to Snowflake as a demo service user, or as `admin`.

    The database is the per-run e2e database. The service passwords come from the
    process environment (the dev `.env`, loaded by `task e2e`), and the admin
    credentials from SNOWFLAKE_ADMIN_USER and SNOWFLAKE_ADMIN_PASSWORD.
    """
    account = os.environ["SNOWFLAKE_ACCOUNT"]
    if user == "admin":
        return snowflake.connector.connect(
            account=account,
            user=os.environ["SNOWFLAKE_ADMIN_USER"],
            password=os.environ["SNOWFLAKE_ADMIN_PASSWORD"],
            role="ACCOUNTADMIN",
            warehouse=SNOWFLAKE_USERS["dbt_runner"].warehouse,
            database=E2E_DATABASE,
        )
    login = SNOWFLAKE_USERS[user]
    return snowflake.connector.connect(
        account=account,
        user=login.user,
        password=os.environ[login.password_variable],
        role=login.role,
        warehouse=login.warehouse,
        database=E2E_DATABASE,
    )


def sf_query(
    sql: str, user: str = "dbt_runner", params: Sequence[Any] | None = None
) -> list[tuple[Any, ...]]:
    """Run a statement on the e2e database as `user` and return all rows.

    Defaults to `dbt_runner`, which can read RAW, STAGING and MARTS. Pass another
    user to test grants: Snowflake errors (denied, not authorized) raise
    `DENIED` (a `ProgrammingError`).
    """
    connection = sf_connect(user)
    try:
        cursor = connection.cursor().execute(sql, params)
        return cursor.fetchall() if cursor.description else []
    finally:
        connection.close()


def compose(
    *args: str, profiles: Sequence[str] = (), check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run `docker compose` against the isolated e2e project."""
    cmd = [
        "docker",
        "compose",
        "-p",
        PROJECT,
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(REPO_ROOT / "docker-compose.yml"),
        *(arg for p in profiles for arg in ("--profile", p)),
        *args,
    ]
    return subprocess.run(  # noqa: S603
        cmd,
        cwd=REPO_ROOT,
        check=check,
        capture_output=True,
        text=True,
        env=process_env(),
    )


def compose_run(service: str, *args: str, profiles: Sequence[str] = ()) -> str:
    """Run a one-shot service (`run --rm`) and return its stdout."""
    return compose("run", "--rm", "-T", service, *args, profiles=profiles).stdout


def run_el(
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the EL one-shot (building it first) and return the finished process.

    Never raises on a non-zero exit: callers assert on `returncode`. `env`
    overrides container variables, e.g. a bogus `SNOWFLAKE_ACCOUNT`.
    """
    profiles = ("core", "el")
    compose("build", "el", profiles=profiles)
    flags = [
        arg for key, value in (env or {}).items() for arg in ("-e", f"{key}={value}")
    ]
    return compose("run", "--rm", "-T", *flags, "el", profiles=profiles, check=False)


def run_dbt(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the dbt one-shot (building it first) and return the finished process.

    Artifacts go to `target/e2e` so the dev stack's `target/` stays untouched.
    Never raises on a non-zero exit: callers assert on `returncode`.
    """
    profiles = ("core", "dbt")
    compose("build", "dbt", profiles=profiles)
    return compose(
        "run",
        "--rm",
        "-T",
        "-e",
        "DBT_TARGET_PATH=target/e2e",
        "dbt",
        *args,
        profiles=profiles,
        check=False,
    )


def container_health() -> dict[str, str]:
    """Map compose service name to its health status (or state if no check)."""
    out = compose("ps", "--all", "--format", "{{.Service}} {{.Health}}").stdout
    return dict(line.split(" ", 1) for line in out.splitlines() if " " in line)


def web_client(headers: Mapping[str, str] | None = None) -> httpx.Client:
    """HTTP client for the web app, optionally with fixed request headers."""
    return httpx.Client(
        base_url=f"http://127.0.0.1:{ENV['WEB_PORT']}", headers=headers, timeout=10
    )


def pg_query_as(
    user: str, password: str, sql: str, db: str = "app"
) -> list[tuple[Any, ...]]:
    """Run a query on the e2e Postgres as a given role (to test grants)."""
    with psycopg.connect(
        host="127.0.0.1",
        port=int(ENV["POSTGRES_PORT"]),
        user=user,
        password=password,
        dbname=db,
        autocommit=True,
    ) as conn:
        cur = conn.execute(sql)  # type: ignore[arg-type]
        return cur.fetchall() if cur.description else []


def migrate(revision: str = "head", *, direction: str = "upgrade") -> str:
    """Run Alembic against the e2e Postgres (same command as `task migrate`)."""
    env = {k: v for k, v in os.environ.items() if k != "ALEMBIC_DATABASE_URL"}
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "uv",
            "run",
            "--package",
            "web",
            "alembic",
            "-c",
            "apps/web/alembic.ini",
            direction,
            revision,
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**env, **ENV, "POSTGRES_HOST": "127.0.0.1"},
    )
    return result.stdout + result.stderr
