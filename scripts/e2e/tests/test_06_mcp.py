"""Stage 6: dbt-mcp over stdio exposes read-only tools and reads as mcp_reader.

Runs after stage 5, so the marts exist. The MCP session is the same command
Claude runs (`scripts/mcp_smoke.py`), pointed at the e2e compose project. Only
the local tools are exercised: the Semantic Layer is served by the dbt platform
from the dev database, not from this run's database. `task mcp:smoke` covers it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import anyio
import pytest

from scripts.e2e.helpers import (
    E2E_DATABASE,
    ENV_FILE,
    PROJECT,
    compose,
    process_env,
    run_dbt,
    sf_query,
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

pytestmark = pytest.mark.usefixtures("e2e_database")

E2E_PROJECT_ARGS = ("-p", PROJECT, "--env-file", str(ENV_FILE))
# Query types that change data or objects. ALTER_SESSION is session setup.
WRITE_QUERY_PREFIXES = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "CREATE",
    "DROP",
    "TRUNCATE",
    "COPY",
    "GRANT",
    "REVOKE",
)
Session = tuple[SmokeResult, datetime, datetime]


@pytest.fixture(scope="module")
def session() -> Session:
    """One MCP session (initialize, list tools, show) and its time window."""
    ensure_mountpoints()
    compose("build", "dbt-mcp", profiles=("core", "mcp"))
    start = datetime.now(UTC) - timedelta(seconds=10)
    result = anyio.run(
        lambda: run_smoke(
            compose_command(E2E_PROJECT_ARGS), process_env(), semantic_layer=False
        )
    )
    return result, start, datetime.now(UTC) + timedelta(seconds=10)


def test_only_allowlisted_tools(session: Session) -> None:
    tools = set(session[0].tools)
    assert tools == ALLOWED_TOOLS
    assert not tools & WRITE_TOOLS


def test_show_answers_top_browsers(session: Session) -> None:
    expected = sf_query(
        "SELECT browser, submissions_count FROM MARTS.MART_BROWSER_DISTRIBUTION"
    )
    rows = session[0].rows
    assert {r["browser"]: r["submissions_count"] for r in rows} == dict(expected)


def test_mcp_session_read_only_as_mcp_reader(session: Session) -> None:
    _, start, end = session
    rows = sf_query(
        "SELECT user_name, query_type, query_text"
        " FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER("
        "USER_NAME => 'MCP_READER',"
        " END_TIME_RANGE_START => %s::TIMESTAMP_LTZ,"
        " END_TIME_RANGE_END => %s::TIMESTAMP_LTZ, RESULT_LIMIT => 1000))"
        " WHERE database_name = %s",
        "admin",
        params=(start.isoformat(), end.isoformat(), E2E_DATABASE),
    )
    assert rows, "the MCP session ran no queries"
    assert {user for user, _, _ in rows} == {"MCP_READER"}
    kinds = {kind for _, kind, _ in rows}
    assert not [k for k in kinds if k.startswith(WRITE_QUERY_PREFIXES)], kinds
    assert any("MART_BROWSER_DISTRIBUTION" in text.upper() for *_, text in rows)


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
    assert "not authorized" in (result.stdout + result.stderr).lower()
