"""Small typed helpers shared by e2e stages: Postgres, ClickHouse, compose, HTTP."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
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


def container_health() -> dict[str, str]:
    """Map compose service name to its health status (or state if no check)."""
    out = compose("ps", "--all", "--format", "{{.Service}} {{.Health}}").stdout
    return dict(line.split(" ", 1) for line in out.splitlines() if " " in line)


def web_client() -> httpx.Client:
    """HTTP client for the web app (used from the submissions stage on)."""
    return httpx.Client(base_url=f"http://127.0.0.1:{ENV['WEB_PORT']}", timeout=10)
