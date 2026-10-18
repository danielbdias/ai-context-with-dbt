"""Postgres access: connection pool and the few statements the app needs.

The `web_writer` role may only INSERT, read `auth_attempts` and read the
`id` column of `submissions`, so nothing here updates or reads messages.
"""

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

from web.settings import Settings
from web.ua import Client

ROLE = "web_writer"
POOL_TIMEOUT_SECONDS = 3.0


def make_pool(settings: Settings) -> ConnectionPool:
    """Create a closed pool; call `open()` to start it."""
    conninfo = make_conninfo(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=ROLE,
        password=settings.postgres_web_writer_password.get_secret_value(),
    )
    return ConnectionPool(
        conninfo,
        min_size=1,
        max_size=5,
        timeout=POOL_TIMEOUT_SECONDS,
        open=False,
    )


def check_database(pool: ConnectionPool) -> bool:
    """Return True when a trivial query succeeds."""
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
    except psycopg.Error:
        return False
    return True


def count_recent_failures(
    conn: psycopg.Connection, ip_hash: str, window_seconds: int
) -> int:
    """Count wrong-password attempts from `ip_hash` inside the window."""
    row = conn.execute(
        "SELECT count(*) FROM app.auth_attempts"
        " WHERE ip_hash = %s AND NOT success AND reason = 'bad_password'"
        " AND attempted_at > now() - make_interval(secs => %s)",
        (ip_hash, window_seconds),
    ).fetchone()
    return int(row[0]) if row else 0


def record_attempt(
    conn: psycopg.Connection,
    ip_hash: str,
    reason: str,
    submission_id: int | None = None,
) -> None:
    """Insert one audit row; success is derived from the reason."""
    conn.execute(
        "INSERT INTO app.auth_attempts (ip_hash, success, reason, submission_id)"
        " VALUES (%s, %s, %s, %s)",
        (ip_hash, reason == "ok", reason, submission_id),
    )


def save_submission(
    conn: psycopg.Connection,
    *,
    message: str,
    client: Client,
    user_agent: str,
    accept_language: str | None,
    ip_hash: str,
) -> int:
    """Insert submission, request metadata and the audit row; return the id.

    Run inside one transaction (the caller's connection block): the grants
    forbid UPDATE, so the audit row is written last with the final id.
    """
    row = conn.execute(
        "INSERT INTO app.submissions (message, browser_family, os_family)"
        " VALUES (%s, %s, %s) RETURNING id",
        (message, client.browser_family, client.os_family),
    ).fetchone()
    if row is None:
        raise RuntimeError("INSERT ... RETURNING returned no row")
    submission_id = int(row[0])
    conn.execute(
        "INSERT INTO app.request_metadata"
        " (submission_id, user_agent_raw, ip_hash, accept_language)"
        " VALUES (%s, %s, %s, %s)",
        (submission_id, user_agent, ip_hash, accept_language),
    )
    record_attempt(conn, ip_hash, "ok", submission_id)
    return submission_id
