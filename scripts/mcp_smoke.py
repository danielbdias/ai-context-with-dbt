"""Smoke-test the dbt-mcp server over stdio, the way Claude launches it.

Starts `docker compose ... run --rm -i --no-TTY dbt-mcp`, initializes an MCP
session and checks that exactly the allowlisted tools are exposed: six local
ones and six Semantic Layer ones. It then asks two questions:

1. "what are the top browsers?" through `show`, which runs on Snowflake as the
   read-only `mcp_reader`.
2. "how many submissions are there?" through the Semantic Layer
   (`query_metrics`, served by the dbt platform), and checks that the answer
   equals a plain `count(*)` on the mart.

    task mcp:smoke

Needs DBT_HOST, DBT_TOKEN and DBT_PROD_ENV_ID in .env (docs/semantic-layer.md).
The image must be built first (`task mcp:build`): stdout is the JSON-RPC
stream, so nothing may be built or pulled on the way.
"""

from __future__ import annotations

import json
import os
import re
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
LOCAL_TOOLS = frozenset(
    {"show", "list", "compile", "parse", "get_node_details_dev", "get_lineage_dev"}
)
SEMANTIC_LAYER_TOOLS = frozenset(
    {
        "list_metrics",
        "get_dimensions",
        "get_entities",
        "get_dimension_values",
        "query_metrics",
        "get_metrics_compiled_sql",
    }
)
ALLOWED_TOOLS = LOCAL_TOOLS | SEMANTIC_LAYER_TOOLS
WRITE_TOOLS = frozenset({"build", "run", "test", "clone", "docs"})
EXPECTED_METRICS = ("submissions_count", "mobile_share", "submissions_7d_rolling")
METRIC = "submissions_count"
TOTAL_SQL = "select count(*) as total from {{ ref('fct_submissions') }}"
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
    # The Semantic Layer half is None when it was not asked for (the e2e suite
    # points at a throwaway database that the dbt platform does not serve).
    metrics_listing: str | None = None
    warehouse_total: int | None = None
    metric_answer: str | None = None


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
    """Extract the JSON rows that `dbt show --output json` prints.

    Snowflake upper-cases column names, so keys are lower-cased.
    """
    for line in text.splitlines():
        if line.lstrip().startswith("["):
            return [{k.lower(): v for k, v in row.items()} for row in json.loads(line)]
    raise ValueError(f"no JSON rows in show output:\n{text}")


def contains_number(text: str, number: int) -> bool:
    """True when `number` appears as a whole number in free-form tool output."""
    return any(int(match) == number for match in re.findall(r"\d+", text))


def tool_text(result: CallToolResult) -> str:
    """Join the text parts of a tool result, raising if the tool failed."""
    text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
    if result.isError:
        raise RuntimeError(f"tool failed:\n{text}")
    return text


async def run_smoke(
    command: Sequence[str],
    env: Mapping[str, str] | None = None,
    *,
    semantic_layer: bool = True,
) -> SmokeResult:
    """Launch the server, list its tools and ask for the top browsers.

    With `semantic_layer`, also ask the dbt platform for a metric. That needs
    DBT_HOST, DBT_TOKEN and DBT_PROD_ENV_ID.
    """
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
        browsers = await session.call_tool(
            "show", {"sql_query": TOP_BROWSERS_SQL, "limit": 10}
        )
        rows = parse_rows(tool_text(browsers))
        if not semantic_layer:
            return SmokeResult(tools=tools, rows=rows)
        total = await session.call_tool("show", {"sql_query": TOTAL_SQL, "limit": 1})
        listing = await session.call_tool("list_metrics", {})
        answer = await session.call_tool("query_metrics", {"metrics": [METRIC]})
        return SmokeResult(
            tools=tools,
            rows=rows,
            metrics_listing=tool_text(listing),
            warehouse_total=int(parse_rows(tool_text(total))[0]["total"]),
            metric_answer=tool_text(answer),
        )


def check(result: SmokeResult) -> None:
    """Fail unless the allowlist holds and the metric agrees with the warehouse."""
    if set(result.tools) != ALLOWED_TOOLS:
        raise AssertionError(f"unexpected tools: {result.tools}")
    if WRITE_TOOLS & set(result.tools):
        raise AssertionError(f"write tools exposed: {result.tools}")
    if not result.rows:
        raise AssertionError("show returned no rows")
    if result.metrics_listing is None:
        return
    missing = [m for m in EXPECTED_METRICS if m not in result.metrics_listing]
    if missing:
        raise AssertionError(f"metrics missing from list_metrics: {missing}")
    if not contains_number(result.metric_answer or "", result.warehouse_total or 0):
        raise AssertionError(
            f"{METRIC} disagrees with count(*) = {result.warehouse_total}:\n"
            f"{result.metric_answer}"
        )


def main() -> int:
    """Run the smoke test against the dev stack and print the answer."""
    ensure_mountpoints()
    result = anyio.run(run_smoke, compose_command())
    check(result)
    print("tools:", ", ".join(result.tools))
    print("Q: how many submissions are there? (Semantic Layer)")
    print(f"  {METRIC} = {result.warehouse_total}, matches count(*) on the mart")
    print("Q: what are the top browsers?")
    for rank, row in enumerate(result.rows, start=1):
        print(
            f"  {rank}. {row['browser']}: {row['submissions_count']} submissions"
            f" ({row['pct']}%)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
