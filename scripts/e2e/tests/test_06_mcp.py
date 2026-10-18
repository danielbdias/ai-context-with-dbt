"""Stage 6: dbt-mcp over stdio exposes six read-only tools and reads as mcp_reader.

Runs after stage 5, so the marts exist. The MCP session is the same command
Claude runs (`scripts/mcp_smoke.py`), pointed at the e2e compose project.
"""

from __future__ import annotations

from datetime import datetime

import anyio
import pytest

from scripts.e2e.helpers import (
    E2E_DIR,
    ENV,
    ENV_FILE,
    PROJECT,
    ch_query,
    compose,
    run_dbt,
)
from scripts.mcp_smoke import (
    ALLOWED_TOOLS,
    TOP_BROWSERS_SQL,
    WRITE_TOOLS,
    SmokeResult,
    compose_command,
    ensure_mountpoints,
    parse_rows,
    run_smoke,
)

E2E_PROJECT_ARGS = (
    "-p",
    PROJECT,
    "--env-file",
    str(ENV_FILE),
    "-f",
    str(E2E_DIR / "compose.e2e.yml"),
)
READ_KINDS = {"Select", "Exists"}


def server_now() -> datetime:
    """ClickHouse server time, so the query_log window uses one clock."""
    return ch_query("SELECT now64(6)")[0][0]


@pytest.fixture(scope="module")
def session() -> tuple[SmokeResult, datetime, datetime]:
    """One MCP session (initialize, list tools, show) and its server-time window."""
    ensure_mountpoints()
    compose("build", "dbt-mcp", profiles=("core", "mcp"))
    start = server_now()
    result = anyio.run(run_smoke, compose_command(E2E_PROJECT_ARGS), ENV)
    return result, start, server_now()


def test_only_allowlisted_tools(
    session: tuple[SmokeResult, datetime, datetime],
) -> None:
    tools = set(session[0].tools)
    assert tools == ALLOWED_TOOLS
    assert not tools & WRITE_TOOLS


def test_show_answers_top_browsers(
    session: tuple[SmokeResult, datetime, datetime],
) -> None:
    expected = ch_query(
        "SELECT browser, submissions_count FROM marts.mart_browser_distribution"
        " ORDER BY submissions_count DESC"
    )
    rows = session[0].rows
    assert [(r["browser"], r["submissions_count"]) for r in rows] == expected


def test_mcp_session_read_only_as_mcp_reader(
    session: tuple[SmokeResult, datetime, datetime],
) -> None:
    _, start, end = session
    ch_query("SYSTEM FLUSH LOGS")
    rows = ch_query(
        "SELECT user, query_kind, written_rows, query FROM system.query_log"
        " WHERE type = 'QueryFinish' AND user != 'default'"
        " AND event_time_microseconds BETWEEN {start:DateTime64(6)}"
        " AND {end:DateTime64(6)}",
        parameters={"start": start, "end": end},
    )
    assert rows, "the MCP session ran no queries"
    assert {user for user, _, _, _ in rows} == {"mcp_reader"}
    assert {kind for _, kind, _, _ in rows} <= READ_KINDS
    assert sum(written for _, _, written, _ in rows) == 0
    assert any("mart_browser_distribution" in query for *_, query in rows)


def test_dbt_show_inline_target_mcp_returns_rows() -> None:
    """Plan assert 10: `dbt show --inline ... --target mcp` returns rows."""
    result = run_dbt(
        "show",
        "--inline",
        TOP_BROWSERS_SQL,
        "--target",
        "mcp",
        "--target-path",
        "target/e2e_mcp",
        "--output",
        "json",
        "--quiet",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert parse_rows(result.stdout)


def test_dbt_show_select_non_mart_fails_as_mcp_reader() -> None:
    """Documented limit: `show --select` re-runs a staging model's SQL."""
    result = run_dbt(
        "show",
        "--select",
        "stg_app__submissions",
        "--target",
        "mcp",
        "--target-path",
        "target/e2e_mcp",
    )
    assert result.returncode != 0
    assert "ACCESS_DENIED" in result.stdout + result.stderr
