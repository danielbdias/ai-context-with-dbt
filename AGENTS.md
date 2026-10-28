# AGENTS.md

Local, Dockerized ELT demo that AI agents can query. Flow: Postgres app
(FastAPI form) -> dlt -> ClickHouse `raw` -> dbt v2 `staging` and `marts` ->
dbt Charts and a read-only dbt MCP server for Claude.

> **DEMO ONLY.** The form password `dssbr` is intentionally insecure. Every
> port binds to 127.0.0.1. Never expose a port or reuse the value.

ChatGPT, public MCP endpoints and the dbt Semantic Layer are out of scope.

## Layout

| Path | What lives there |
|---|---|
| `apps/web` | FastAPI + Jinja2 form, Alembic migrations (`migrations/`) |
| `apps/el` | dlt one-shot: `app.submissions` -> `raw.submissions` |
| `transform` | uv package and image for dbt 2.0.8 and dbt-mcp |
| `transform/dbt` | The dbt project: `models/{staging,intermediate,marts}`, `macros`, `seeds`, `tests`, `profiles.yml` (targets `dev`, `ci`, `mcp`, `charts`) |
| `dashboard/charts` | dbt Charts boards (`overview`, `words`); own `uv.lock` and image |
| `infra` | Postgres and ClickHouse init scripts, ClickHouse guardrail config |
| `mcp` | Claude Code and Desktop setup (`.mcp.json` at the root registers `dbt`) |
| `scripts` | `seed.py`, `mcp_smoke.py`, `check_dbt_descriptions.py`, `e2e/` suite |
| `docs` | architecture, PII, grants matrix, agent guide, test strategy, debugging |
| `plan.md`, `spec.md` | Plan and requirements |
| `presentation` | Marp markdown decks |

The root `pyproject.toml` is a uv workspace of `apps/web`, `apps/el` and
`transform`. `dashboard/charts` is excluded and has its own lock.

## Commands

Tool versions come from asdf (`.tool-versions`: Python 3.13, uv, task). Use
`uv`, never `pip`. Everything runs through `task` (`task --list`).

```bash
task setup          # uv sync, create .env with random secrets, build dbt image
task up             # Postgres, ClickHouse, migrations, web; waits for health
task seed           # POST sample good and bad submissions
task el             # dlt: Postgres -> ClickHouse raw
task dbt:build      # seeds, models, tests (-- --select mart_word_frequencies+)
task dashboard      # dbt Charts
task mcp:smoke      # talk MCP to dbt-mcp over stdio, no GUI
task down           # stop, keep data
task reset          # stop, delete volumes and dbt artifacts
```

Checks:

```bash
task lint                # dbt description coverage, ruff check + format, lock checks, board check
task fmt                 # ruff fix + format
task test                # unit tests (integration and e2e deselected)
task test:integration    # needs `task up` first
task e2e                 # isolated project aictx-e2e, own volumes and ports
```

Run a single test with `uv run pytest apps/web/tests/test_csrf.py`.

## Conventions

- Python 3.13, type hints everywhere, line length 88, ruff with Google-style
  docstrings (`D`) on non-test code. Tests are exempt from `S` and `D` rules.
- Tests: pytest, anyio for async. Mark container-backed tests `integration`
  and compose-project tests `e2e`; both are deselected by default.
- Every dbt model, seed, source and column needs a description. Descriptions
  must not contain a semicolon. `task dbt:coverage` enforces both.
- dbt runs in a container (`task dbt:*`), not on the host. ClickHouse SQL
  dialect: `count()`, `toDate()`, `argMax()`, `lengthUTF8()`.
- Commits follow Conventional Commits (`feat:`, `fix:`, `docs:`, ...).

## Querying the warehouse as an agent

Read [docs/agent-guide.md](docs/agent-guide.md) first. In short:

- Query only `{{ ref('mart_...') }}` or `fct_submissions` via
  `dbt show --inline` (MCP tool `show`). `raw` and `staging` are denied to
  readers, as is `dbt show --select <non-mart model>`.
- No `LIMIT` in the SQL; use the `--limit` flag (MCP: `limit`).
- Prefer narrow queries over `select *` on `fct_submissions` (free-text
  messages).
- Semantic Layer, Discovery API and `execute_sql` are not available locally.

## Security and PII

- One least-privilege database user per service; grants are at database level
  ([docs/grants-matrix.md](docs/grants-matrix.md)). Do not widen them to make
  something work.
- The IP is never stored raw (truncated, then HMAC). Raw user agent and
  language stay in Postgres `request_metadata` and must not reach the
  warehouse ([docs/pii.md](docs/pii.md)).
- Never commit `.env`; `.env.example` holds the `change-me` placeholders.

## Gotchas

- The e2e project uses separate ports (15432, 18123, 19000, 18000, 18090,
  18088, 18081) and never touches the dev stack.
- `task reset` keeps `transform/dbt/target` and `target_mcp` as directories
  because dbt-mcp needs them as mountpoints.
- Build the dbt-mcp image (`task mcp:build`) before starting Claude, which
  launches it over stdio.
- For failures per hop, see [docs/debugging.md](docs/debugging.md).
