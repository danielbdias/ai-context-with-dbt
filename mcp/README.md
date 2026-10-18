# dbt MCP server for Claude

Claude (Code or Desktop) talks to the marts through
[dbt-mcp](https://github.com/dbt-labs/dbt-mcp) 2.7.0 running in a container
over stdio. The container holds dbt-mcp and the dbt v2 binary from the same
locked environment, so nothing is installed on the host and paths never drift.

```
Claude --stdio--> docker compose run dbt-mcp --> dbt v2 (target mcp) --HTTP--> ClickHouse marts
                                                  user mcp_reader, read-only
```

ChatGPT is out of scope for this project.

## Setup

```bash
task up            # ClickHouse must be running (core profile)
task el && task dbt:build   # marts must exist
task mcp:build     # build the image first: stdout is the JSON-RPC stream
task mcp:smoke     # optional: list tools and ask for the top browsers, no GUI
task mcp:claude    # prints the setup below with this machine's paths
```

`task mcp:claude` changes no Claude config. It only builds and prints.

### Claude Code

`.mcp.json` at the repo root declares the server `dbt` (project scope). Its
paths are relative, so start `claude` from the repo root.

1. Run `claude` in the repo root and approve the `dbt` server when asked.
2. `claude mcp list` should show `dbt ... ✔ Connected` (before approval it
   shows `Pending approval`). Inside a session, `/mcp` shows the 6 tools.
3. Ask: "what are the top browsers?"

### Claude Desktop

Desktop does not read `.mcp.json` and starts servers with a minimal `PATH`,
so it needs absolute paths. Copy `mcp/claude_desktop_config.example.json` into
`~/Library/Application Support/Claude/claude_desktop_config.json` (merge the
`mcpServers` key) and replace:

- `/usr/local/bin/docker` with the output of `command -v docker`
  (`/opt/homebrew/bin/docker` with Homebrew).
- `/ABSOLUTE/PATH/TO/ai-context-with-dbt` with the repo path.

`task mcp:claude` prints this JSON with both already filled in. Restart Claude
Desktop afterwards.

## The launch command

```bash
docker compose -f docker-compose.yml --project-directory . \
  --profile core --profile mcp run --rm -i --no-TTY dbt-mcp
```

- `-i --no-TTY`: stdin stays open and stdout is a clean byte stream. Compose
  status lines and dbt-mcp logs go to stderr, so stdout carries JSON-RPC only.
- `--profile core` is needed because the service depends on `clickhouse`. If
  ClickHouse is down, compose starts it (and waits for health) first.
- `--rm`: one container per client session, removed on exit.

## Tools (allowlist)

`DBT_MCP_ENABLE_TOOLS=show,list,compile,parse,get_node_details_dev,get_lineage_dev`
switches dbt-mcp to allowlist mode: only these 6 are registered. `build`,
`run`, `test`, `clone`, `docs`, the Semantic Layer, Discovery, Admin API, SQL,
codegen, LSP and product-docs tools are absent.

| Tool | Arguments | Use |
|---|---|---|
| `show` | `sql_query`, `limit` (default 5) | Run SQL over `{{ ref('mart_...') }}` and get JSON rows |
| `list` | `node_selection`, `resource_type`, `yml_selector` | Find models (`dbt ls`) |
| `get_node_details_dev` | `node_id` (a selector, e.g. `mart_browser_distribution`) | Description, columns, tests |
| `get_lineage_dev` | `unique_id` (e.g. `model.aictx.mart_browser_distribution`), `types`, `depth` | Parents and children |
| `compile` | `node_selection`, `yml_selector` | Render a model's SQL (written inside the container) |
| `parse` | (none) | Re-parse the project (refresh the manifest) |

`show` details:

- Put no `LIMIT` in `sql_query`. Pass `limit` instead. If the SQL contains the
  word "limit" anywhere, dbt-mcp switches to `--limit -1` (no cap from dbt,
  but the ClickHouse 10,000-row cap still applies).
- Use ClickHouse SQL: `count()`, `toDate()`, `argMax()`.

## Guardrails

Each layer holds on its own:

| Layer | What it does |
|---|---|
| Tool allowlist | Only the 6 tools above exist. No tool builds, runs or tests models. |
| dbt target `mcp` | `DBT_TARGET=mcp` connects as `mcp_reader` with schema `marts`. Only `CLICKHOUSE_MCP_READER_PASSWORD` is passed to the container. |
| ClickHouse grants | `mcp_reader` has `SELECT ON marts.*` and nothing else: no `raw`, `staging`, `system.query_log` or writes. A `show` that tries `INSERT` fails with `ACCESS_DENIED`. |
| Settings profile `reader` | `readonly=2`, at most 30 s, 10,000 rows and 1 GB per query, `result_overflow_mode='throw'` pinned. See `docs/grants-matrix.md`. |
| Container | Project mounted read-only. dbt writes only to an in-memory volume (`target_mcp/`), logs to `/tmp`. No ports, 512 MB, no secrets other than the reader password. |

Reading non-mart models fails by design: a `show` over
`ref('stg_app__submissions')`, or the CLI's `show --select stg_app__submissions`
(which re-runs the model's SQL against `raw` and `staging`), returns
`ACCESS_DENIED`.

## Artifacts: `target_mcp/`

`DBT_TARGET_PATH=target_mcp` sends dbt's manifest and compiled SQL to
`target_mcp/`, never to the dev `target/`. dbt-mcp's `get_lineage_dev` reads
`target/manifest.json` (hard-coded), so compose mounts the same in-memory
volume (`dbt_mcp_target`) at both `target_mcp/` and `target/` inside the
container. The host's `target/` and `target_mcp/` are only mountpoints and
stay untouched. `task mcp:build` creates them, because Docker cannot create a
mountpoint inside a read-only bind mount.

## Debugging

- Server logs (stderr): set `DBT_MCP_LOG_LEVEL=DEBUG` in `.env`.
- What ran in ClickHouse: `task ch -- -q "SELECT event_time, query_kind,
  query FROM system.query_log WHERE user = 'mcp_reader' ORDER BY event_time
  DESC LIMIT 20"`.
- Run dbt directly in the same container:
  `docker compose --profile core --profile mcp run --rm --entrypoint dbt dbt-mcp debug`.
- A harmless stderr line, `Failed to open log file for append: Read-only file
  system`, comes from dbt-mcp starting `dbt lsp` eagerly (it does so whenever
  the dbt binary has an `lsp` command, even with LSP tools disabled). The
  read-only project stops it, which is what we want: no LSP tools are exposed.
- The `Could not resolve credentials ... DBT_HOST` warning only means the dbt
  platform tools are off, as intended.
