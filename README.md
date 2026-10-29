# ai-context-with-dbt

**English** | [Português (Brasil)](README.pt-br.md)

A Dockerized ELT demo that AI agents can query, with a Semantic Layer:

Postgres app -> dlt -> Snowflake `RAW` -> dbt v2 `STAGING` and `MARTS` -> dbt
Charts, and a read-only dbt MCP server for Claude that can run `show` over the
marts or ask the dbt platform's Semantic Layer for metrics.

> **DEMO ONLY.** The form password `dssbr` is intentionally insecure and for
> the demo. Do not expose any port beyond localhost or reuse the value. Every
> container port binds to 127.0.0.1, but the warehouse (Snowflake) and the
> Semantic Layer (dbt platform) are remote services, so this no longer runs
> offline and it costs warehouse credits.

ChatGPT and public MCP endpoints are out of scope.

## Prerequisites

- [asdf](https://asdf-vm.com/) with the tools in `.tool-versions` (Python,
  uv, task): `asdf install`
- Docker with Compose (Docker Desktop or similar), about 6 GB of free RAM
- `openssl` (used by `task setup` to generate secrets)
- A **Snowflake** account, and an admin user that can use `ACCOUNTADMIN` (it
  creates the database, roles, users and warehouses)
- A **dbt platform** account (Starter or higher) for the Semantic Layer. Without
  it everything else works, and the metric tools return an error

## Quickstart

```bash
task setup        # uv sync, create .env with random secrets, build the dbt image
# edit .env: SNOWFLAKE_ACCOUNT=orgname-accountname
export SNOWFLAKE_ADMIN_USER=... SNOWFLAKE_ADMIN_PASSWORD=...
task snowflake:setup   # once: database, roles, users, warehouses and grants
task up           # Postgres, migrations and the web app, waits for health
task seed         # POST sample good and bad submissions
task seed:history # optional: about 60 days of backdated rows for the metrics
task el           # dlt: Postgres submissions -> Snowflake RAW
task dbt:build    # seeds, models and tests (STAGING, MARTS)
task dashboard    # dbt Charts; opens the overview board
```

The Semantic Layer is set up once in the dbt platform: follow
[docs/semantic-layer.md](docs/semantic-layer.md), then put `DBT_HOST`,
`DBT_HOST_PREFIX`, `DBT_TOKEN` and `DBT_PROD_ENV_ID` in `.env`.

```bash
task mcp:claude   # build dbt-mcp and print the Claude Code and Desktop setup
task mcp:smoke    # no GUI: tools, top browsers, and a metric equal to count(*)
task e2e          # end-to-end suite (own project, per-run Snowflake database)
```

Then open the form (`task app:open`), submit a few messages, and rerun
`task el && task dbt:build`. For Claude Code, run `claude` from the repo root,
approve the `dbt` server and ask "what are the top browsers?" or "what share of
submissions came from phones, by month?".

`task --list` shows everything else. `task down` stops the stack and keeps
data. `task reset` also deletes the Postgres volume and the dbt artifacts in
`transform/dbt/target`. It does not touch Snowflake.

## Ports (127.0.0.1 only)

| Port | Service | Task |
|---|---|---|
| 8000 | Web form | `task up` |
| 5432 | Postgres | `task up` |
| 8090 | dbt Charts (`/overview/`, `/words/`) | `task dashboard` |
| 8081 | dbt docs | `task dbt:docs` |

The e2e project uses 15432, 18000, 18090 and 18081. If another Postgres already
uses 5432 on your machine, set `POSTGRES_PORT` in `.env` (see
[docs/debugging.md](docs/debugging.md)).

## Docs

- [docs/architecture.md](docs/architecture.md): diagram, components, data flow
- [docs/semantic-layer.md](docs/semantic-layer.md): setting up the dbt platform
- [docs/pii.md](docs/pii.md): what is stored and where
- [docs/grants-matrix.md](docs/grants-matrix.md): who can read what
- [docs/agent-guide.md](docs/agent-guide.md): how agents should query the marts and metrics
- [mcp/README.md](mcp/README.md): Claude Code and Desktop setup
- [dashboard/charts/README.md](dashboard/charts/README.md): the dbt Charts boards
- [docs/test-strategy.md](docs/test-strategy.md): test pyramid, gates, e2e map
- [docs/debugging.md](docs/debugging.md): per-hop debugging and known failure modes
- [plan.md](plan.md) and [spec.md](spec.md): the original plan and requirements
  (the ClickHouse design, superseded by the migration described above)
