"""Smoke-test the dbt-mcp server over stdio, the way Claude launches it.

Starts `docker compose ... run --rm -i --no-TTY dbt-mcp`, initializes an MCP
session, checks that exactly the six allowlisted tools are exposed and asks
"what are the top browsers?" through the `show` tool.

    task mcp:build && uv run python scripts/mcp_smoke.py

The image must be built first (`task mcp:build`): stdout is the JSON-RPC
stream, so nothing may be built or pulled on the way.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = REPO_ROOT / "transform" / "dbt"
ALLOWED_TOOLS = frozenset(
    {"show", "list", "compile", "parse", "get_node_details_dev", "get_lineage_dev"}
)
WRITE_TOOLS = frozenset({"build", "run", "test", "clone", "docs"})
TOP_BROWSERS_SQL = (
    "select browser, submissions_count, pct"
    " from {{ ref('mart_browser_distribution') }}"
    " order by submissions_count desc"
)


@dataclass(frozen=True)
class SmokeResult:
    """What the server exposed and what it answered."""

    tools: list[str]
    rows: list[dict[str, Any]]


def compose_command(project_args: Sequence[str] = ()) -> list[str]:
    """The stdio launch command used by `.mcp.json`, plus optional project args."""
    return [
        "docker",
        "compose",
        "-f",
        str(REPO_ROOT / "docker-compose.yml"),
        "--project-directory",
        str(REPO_ROOT),
        *project_args,
        "--profile",
        "core",
        "--profile",
        "mcp",
        "run",
        "--rm",
        "-i",
        "--no-TTY",
        "dbt-mcp",
    ]


def ensure_mountpoints() -> None:
    """Create the host dirs that the read-only project mount needs as mountpoints."""
    for name in ("target", "target_mcp"):
        (DBT_DIR / name).mkdir(exist_ok=True)


def parse_rows(text: str) -> list[dict[str, Any]]:
    """Extract the JSON rows that `dbt show --output json` prints."""
    for line in text.splitlines():
        if line.lstrip().startswith("["):
            return json.loads(line)
    raise ValueError(f"no JSON rows in show output:\n{text}")


def tool_text(result: CallToolResult) -> str:
    """Join the text parts of a tool result, raising if the tool failed."""
    text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
    if result.isError:
        raise RuntimeError(f"tool failed:\n{text}")
    return text


async def run_smoke(
    command: Sequence[str], env: Mapping[str, str] | None = None
) -> SmokeResult:
    """Launch the server, list its tools and ask for the top browsers."""
    params = StdioServerParameters(
        command=command[0],
        args=list(command[1:]),
        env={**os.environ, **(env or {})},
        cwd=REPO_ROOT,
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = sorted(tool.name for tool in (await session.list_tools()).tools)
        result = await session.call_tool(
            "show", {"sql_query": TOP_BROWSERS_SQL, "limit": 10}
        )
        return SmokeResult(tools=tools, rows=parse_rows(tool_text(result)))


def check(result: SmokeResult) -> None:
    """Fail unless exactly the allowlisted tools are exposed and rows came back."""
    if set(result.tools) != ALLOWED_TOOLS:
        raise AssertionError(f"unexpected tools: {result.tools}")
    if WRITE_TOOLS & set(result.tools):
        raise AssertionError(f"write tools exposed: {result.tools}")
    if not result.rows:
        raise AssertionError("show returned no rows")


def main() -> int:
    """Run the smoke test against the dev stack and print the answer."""
    ensure_mountpoints()
    result = anyio.run(run_smoke, compose_command())
    check(result)
    print("tools:", ", ".join(result.tools))
    print("Q: what are the top browsers?")
    for rank, row in enumerate(result.rows, start=1):
        print(
            f"  {rank}. {row['browser']}: {row['submissions_count']} submissions"
            f" ({row['pct']}%)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
