# dbt MCP server for Claude

Claude (Code or Desktop) talks to the marts through
[dbt-mcp](https://github.com/dbt-labs/dbt-mcp) 2.7.0 running in a container
over stdio. The container holds dbt-mcp and the dbt v2 binary from the same
locked environment, so nothing is installed on the host and paths never drift.

```
                                  +--> dbt v2 (target mcp) ------------> Snowflake MARTS
Claude --stdio--> dbt-mcp (Docker)|     user MCP_READER, read-only
                                  +--> dbt platform Semantic Layer ----> Snowflake MARTS
                                        service token, metrics only      user MCP_READER
```

Two paths answer questions. `show` writes SQL over a mart. The Semantic Layer
tools ask for a metric by name (`submissions_count`, `mobile_share`, ...) and
let MetricFlow generate the SQL, so a definition lives in one place.

ChatGPT is out of scope for this project.

## Setup

```bash
task el && task dbt:build   # marts must exist in Snowflake
task mcp:build     # build the image first: stdout is the JSON-RPC stream
task mcp:smoke     # optional: list tools, top browsers and a metric, no GUI
task mcp:claude    # prints the setup below with this machine's paths
```

The Semantic Layer tools also need the dbt platform. Do
[docs/semantic-layer.md](../docs/semantic-layer.md) first, then put
`DBT_HOST`, `DBT_TOKEN` and `DBT_PROD_ENV_ID` in `.env`, plus `DBT_HOST_PREFIX`
when the host looks like `<prefix>.<cell>.dbt.com`. Without them the
server still starts and `show` works, but the metric tools return an error.

`task mcp:claude` changes no Claude config. It only builds and prints.

### Claude Code

`.mcp.json` at the repo root declares the server `dbt` (project scope). Its
paths are relative, so start `claude` from the repo root.

1. Run `claude` in the repo root and approve the `dbt` server when asked.
2. `claude mcp list` should show `dbt ... ✔ Connected` (before approval it
   shows `Pending approval`). Inside a session, `/mcp` shows the 12 tools.
3. Ask: "what are the top browsers?" (`show`) or "what share of submissions
   came from phones, per day this month?" (Semantic Layer).

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
- `--profile core` is kept for the compose project name and profile set. The
  service has no local dependencies: the warehouse and the platform are remote.
- `--rm`: one container per client session, removed on exit.

## Tools (allowlist)

`DBT_MCP_ENABLE_TOOLS` switches dbt-mcp to allowlist mode: only these 12 are
registered. `build`, `run`, `test`, `clone`, `docs`, Discovery, Admin API, SQL
(`execute_sql`), codegen, LSP and product-docs tools are absent.

Local tools, run by dbt v2 as `mcp_reader`:

| Tool | Arguments | Use |
|---|---|---|
| `show` | `sql_query`, `limit` (default 5) | Run SQL over `{{ ref('mart_...') }}` and get JSON rows |
| `list` | `node_selection`, `resource_type`, `yml_selector` | Find models (`dbt ls`) |
| `get_node_details_dev` | `node_id` (a selector, e.g. `mart_browser_distribution`) | Description, columns, tests |
| `get_lineage_dev` | `unique_id` (e.g. `model.aictx.mart_browser_distribution`), `types`, `depth` | Parents and children |
| `compile` | `node_selection`, `yml_selector` | Render a model's SQL (written inside the container) |
| `parse` | (none) | Re-parse the project (refresh the manifest) |

Semantic Layer tools, served by the dbt platform (read-only):

| Tool | Arguments | Use |
|---|---|---|
| `list_metrics` | (none) | What can I ask for, with descriptions |
| `get_dimensions` | `metrics` | How can these metrics be sliced |
| `get_entities` | `metrics` | Entities (join keys) of these metrics |
| `get_dimension_values` | `metrics`, `group_by` | Valid values, for example the browsers |
| `query_metrics` | `metrics`, `group_by`, `where`, `order_by`, `limit` | Compute metrics |
| `get_metrics_compiled_sql` | same as `query_metrics` | The SQL MetricFlow would run |

`show` details:

- Put no `LIMIT` in `sql_query`. Pass `limit` instead. If the SQL contains the
  word "limit" anywhere, dbt-mcp switches to `--limit -1` (no cap from dbt).
- Use Snowflake SQL: `count(*)`, `max_by()`, `convert_timezone()`.
- Column names come back upper case (`BROWSER`, `N`), because Snowflake folds
  unquoted aliases. Quote an alias to keep its case.

`query_metrics` details:

- Group by time with `metric_time` and a grain, for example day or month.
  Dimensions are named `submission__browser`, `submission__os` and
  `submission__is_mobile` (the entity name, two underscores, the dimension).
- Prefer a metric over SQL when one exists. `mobile_share` and
  `submissions_wow_growth` are easy to get wrong by hand.

## Guardrails

Each layer holds on its own:

| Layer | What it does |
|---|---|
| Tool allowlist | Only the 12 tools above exist. No tool builds, runs or tests models. |
| dbt target `mcp` | `DBT_TARGET=mcp` connects as `MCP_READER` with role `AICTX_MCP_READER`. Only `SNOWFLAKE_MCP_READER_PASSWORD` is passed for the warehouse. |
| Snowflake grants | The role has `SELECT` on `MARTS` and nothing else: no `RAW`, no `STAGING`, no writes. A `show` that tries `INSERT` or reads `RAW` fails with a "does not exist or not authorized" error. |
| Query cap | The reader warehouse and user have a 30 s statement timeout, and a resource monitor suspends the warehouses at the monthly credit quota. Snowflake has no read-only flag, row cap or memory cap, so grants alone make the role read-only. See `docs/grants-matrix.md`. |
| Platform token | `DBT_TOKEN` is a service token with the permission sets Semantic Layer Only and Metadata Only. The Semantic Layer queries with its own read-only credential (the same `MCP_READER`). |
| Container | Project mounted read-only. dbt writes only to an in-memory volume (`target_mcp/`), logs to `/tmp`. No ports, 512 MB. Secrets passed in: the reader password and the platform token. |

`DBT_TOKEN` can query every metric. Keep it in `.env` (git-ignored) and do not
paste it into a client config.

Reading non-mart models fails by design: a `show` over
`ref('stg_app__submissions')`, or the CLI's `show --select stg_app__submissions`
(which re-runs the model's SQL against `RAW`), is refused by the grants.

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
- What ran in Snowflake: as an admin, `SELECT start_time, query_text FROM
  TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(USER_NAME => 'MCP_READER'))
  ORDER BY start_time DESC LIMIT 20`. The `ACCOUNT_USAGE` view has up to 45
  minutes of delay, so prefer the table function. `DBT_RUNNER` only sees its
  own queries, so `task sf` is not enough for this.
- What the Semantic Layer would run: ask for `get_metrics_compiled_sql`.
- Run dbt directly in the same container:
  `docker compose --profile core --profile mcp run --rm --entrypoint dbt dbt-mcp debug`.
- A harmless stderr line, `Failed to open log file for append: Read-only file
  system`, comes from dbt-mcp starting `dbt lsp` eagerly (it does so whenever
  the dbt binary has an `lsp` command, even with LSP tools disabled). The
  read-only project stops it, which is what we want: no LSP tools are exposed.
- The `Could not resolve credentials ... DBT_HOST` warning means the platform
  variables are missing, so the Semantic Layer tools answer with an error. The
  entrypoint (`transform/mcp-entrypoint.sh`) unsets empty `DBT_*` variables,
  because dbt-mcp crashes on an empty `DBT_PROD_ENV_ID`.
- A `Timeout waiting for LSP server to connect` line on shutdown is harmless.
- `Name or service not known` or `name resolver error: produced zero addresses`
  from a metric tool: dbt-mcp built a host that does not exist. Set
  `DBT_HOST_PREFIX` to the first label of `DBT_HOST` (docs/semantic-layer.md).
- `403 Forbidden` from the platform: the token has the wrong permission sets, or
  your account restricts IP addresses and needs the host's address allowed.
