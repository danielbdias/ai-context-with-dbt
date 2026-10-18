"""Small typed helpers shared by e2e stages: Postgres, ClickHouse, compose, HTTP."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import clickhouse_connect
import httpx
import psycopg

E2E_DIR = Path(__file__).parent
REPO_ROOT = E2E_DIR.parent.parent
ENV_FILE = E2E_DIR / "e2e.env"
PROJECT = "aictx-e2e"


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse a simple KEY=VALUE env file, ignoring blanks and comments."""
    pairs = (
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    return {key.strip(): value.strip() for key, value in pairs}


ENV = load_env()


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


def ch_query(
    sql: str,
    user: str = "default",
    password: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> list[tuple[Any, ...]]:
    """Run a query on the e2e ClickHouse and return rows.

    Defaults to the admin user. Pass `user`/`password` to test grants: server
    errors (denied, constraint violations) raise clickhouse_connect exceptions.
    """
    if password is None:
        password = ENV["CLICKHOUSE_DEFAULT_PASSWORD"] if user == "default" else ""
    client = clickhouse_connect.get_client(
        host="127.0.0.1",
        port=int(ENV["CLICKHOUSE_HTTP_PORT"]),
        username=user,
        password=password,
    )
    try:
        return list(client.query(sql, parameters=parameters).result_rows)
    finally:
        client.close()


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
        "-f",
        str(E2E_DIR / "compose.e2e.yml"),
        *(arg for p in profiles for arg in ("--profile", p)),
        *args,
    ]
    return subprocess.run(  # noqa: S603
        cmd,
        cwd=REPO_ROOT,
        check=check,
        capture_output=True,
        text=True,
        env={**os.environ, **ENV},
    )


def compose_run(service: str, *args: str, profiles: Sequence[str] = ()) -> str:
    """Run a one-shot service (`run --rm`) and return its stdout."""
    return compose("run", "--rm", "-T", service, *args, profiles=profiles).stdout


def run_el(
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the EL one-shot (building it first) and return the finished process.

    Never raises on a non-zero exit: callers assert on `returncode`. `env`
    overrides container variables, e.g. a bogus `CLICKHOUSE_HOST`.
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


def ch_command(sql: str, user: str = "default", password: str | None = None) -> None:
    """Run a statement without a result set (DDL, INSERT) on ClickHouse."""
    if password is None:
        password = ENV["CLICKHOUSE_DEFAULT_PASSWORD"] if user == "default" else ""
    client = clickhouse_connect.get_client(
        host="127.0.0.1",
        port=int(ENV["CLICKHOUSE_HTTP_PORT"]),
        username=user,
        password=password,
    )
    try:
        client.command(sql)
    finally:
        client.close()


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
