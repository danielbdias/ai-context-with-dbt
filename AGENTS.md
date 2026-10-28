# AGENTS.md

Dockerized ELT demo that AI agents can query, with a Semantic Layer. Flow:
Postgres app (FastAPI form) -> dlt -> Snowflake `RAW` -> dbt v2 `STAGING` and
`MARTS` -> dbt Charts and a read-only dbt MCP server for Claude. Metrics are
served by the dbt platform (Semantic Layer) from `MARTS`.

> **DEMO ONLY.** The form password `dssbr` is intentionally insecure. Every
> container port binds to 127.0.0.1. Never expose a port or reuse the value.
> Snowflake and the dbt platform are remote, so this needs network access and
> costs warehouse credits.

ChatGPT and public MCP endpoints are out of scope.

## Layout

| Path | What lives there |
|---|---|
| `apps/web` | FastAPI + Jinja2 form, Alembic migrations (`migrations/`) |
| `apps/el` | dlt one-shot: `app.submissions` -> `RAW.SUBMISSIONS` |
| `transform` | uv package and image for dbt 2.0.8 and dbt-mcp |
| `transform/dbt` | The dbt project: `models/{staging,intermediate,marts}`, `macros`, `seeds`, `tests`, `profiles.yml` (targets `dev`, `ci`, `mcp`, `charts`) |
| `dashboard/charts` | dbt Charts boards (`overview`, `words`); own `uv.lock` and image |
| `infra` | Postgres init scripts and `snowflake/setup.sql` (database, roles, users, warehouses, grants) |
| `mcp` | Claude Code and Desktop setup (`.mcp.json` at the root registers `dbt`) |
| `scripts` | `seed.py`, `seed_history.py`, `snowflake_setup.py`, `mcp_smoke.py`, `check_dbt_descriptions.py`, `e2e/` suite |
| `docs` | architecture, Semantic Layer setup, PII, grants matrix, agent guide, test strategy, debugging |
| `plan.md`, `spec.md` | Original plan and requirements (ClickHouse design, superseded) |
| `presentation` | Marp markdown decks |

The root `pyproject.toml` is a uv workspace of `apps/web`, `apps/el` and
`transform`. `dashboard/charts` is excluded and has its own lock.

## Commands

Tool versions come from asdf (`.tool-versions`: Python 3.13, uv, task). Use
`uv`, never `pip`. Everything runs through `task` (`task --list`).

```bash
task setup          # uv sync, create .env with random secrets, build dbt image
task snowflake:setup # once: database, roles, users, grants (needs SNOWFLAKE_ADMIN_*)
task up             # Postgres, migrations, web; waits for health
task seed           # POST sample good and bad submissions
task seed:history   # about 60 days of backdated rows, for the metrics
task el             # dlt: Postgres -> Snowflake RAW
task dbt:build      # seeds, models, tests (-- --select mart_word_frequencies+)
task dashboard      # dbt Charts
task mcp:smoke      # dbt-mcp over stdio: tools, a show query and a metric
task sf -- -q '...' # Snowflake SQL as DBT_RUNNER
task down           # stop, keep data
task reset          # stop, delete the Postgres volume and dbt artifacts
```

Checks:

```bash
task lint                # dbt description coverage, ruff check + format, lock checks, board check
task fmt                 # ruff fix + format
task test                # unit tests (integration and e2e deselected)
task test:integration    # needs `task up` first
task e2e                 # project aictx-e2e plus a per-run Snowflake database (needs SNOWFLAKE_ADMIN_*)
```

Run a single test with `uv run pytest apps/web/tests/test_csrf.py`.

## Conventions

- Python 3.13, type hints everywhere, line length 88, ruff with Google-style
  docstrings (`D`) on non-test code. Tests are exempt from `S` and `D` rules.
- Tests: pytest, anyio for async. Mark container-backed tests `integration`
  and compose-project tests `e2e`; both are deselected by default.
- Every dbt model, seed, source and column needs a description. Descriptions
  must not contain a semicolon. `task dbt:coverage` enforces both.
- dbt runs in a container (`task dbt:*`), not on the host. Snowflake SQL
  dialect: `count(*)`, `max_by()`, `convert_timezone()`, `length()`, `qualify`.
  Unquoted names fold to upper case.
- Commits follow Conventional Commits (`feat:`, `fix:`, `docs:`, ...).

## Querying the warehouse as an agent

Read [docs/agent-guide.md](docs/agent-guide.md) first. In short:

- For a number the project defines (counts, `mobile_share`, rolling and
  cumulative totals, week-over-week growth), use the Semantic Layer tools
  (`list_metrics`, `query_metrics`) before writing SQL. They need the dbt
  platform ([docs/semantic-layer.md](docs/semantic-layer.md)).
- Otherwise query only `{{ ref('mart_...') }}` or `fct_submissions` via
  `dbt show --inline` (MCP tool `show`). `RAW` and `STAGING` are denied to
  readers, as is `dbt show --select <non-mart model>`.
- No `LIMIT` in the SQL; use the `--limit` flag (MCP: `limit`).
- Prefer narrow queries over `select *` on `fct_submissions` (free-text
  messages).
- Rolling and cumulative metrics return rows for dates after the last data;
  cap `metric_time`.
- Discovery API, Admin API and `execute_sql` tools are not enabled.

## Security and PII

- One least-privilege database user per service; grants are on schemas, with
  `FUTURE` grants for readers ([docs/grants-matrix.md](docs/grants-matrix.md)).
  Do not widen them to make something work.
- The IP is never stored raw (truncated, then HMAC). Raw user agent and
  language stay in Postgres `request_metadata` and must not reach the
  warehouse ([docs/pii.md](docs/pii.md)).
- Never commit `.env` (it holds the Snowflake passwords and the dbt platform
  token); `.env.example` holds the `change-me` placeholders.

## Gotchas

- The e2e project uses separate ports (15432, 18000, 18090, 18081) and a
  per-run Snowflake database `AICTX_E2E_<id>`. It never touches the dev stack
  or the dev database `AICTX`.
- If another Postgres is bound to 5432 on the host it shadows the container.
  Set `POSTGRES_PORT` in `.env`, and see [docs/debugging.md](docs/debugging.md).
- A dbt platform production job must use the target name `prod`, or models land
  in prefixed schemas ([docs/semantic-layer.md](docs/semantic-layer.md)).
- `task reset` keeps `transform/dbt/target` and `target_mcp` as directories
  because dbt-mcp needs them as mountpoints. It does not touch Snowflake.
- Build the dbt-mcp image (`task mcp:build`) before starting Claude, which
  launches it over stdio.
- For failures per hop, see [docs/debugging.md](docs/debugging.md).
