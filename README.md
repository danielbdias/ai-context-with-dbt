# ai-context-with-dbt

A local, Dockerized ELT demo that AI agents can query:

Postgres app -> dlt -> ClickHouse raw -> dbt v2 staging and marts -> dbt Charts
and a read-only dbt MCP server for Claude.

> **DEMO ONLY.** The form password `dssbr` is intentionally insecure and for
> the local demo. Do not expose any port beyond localhost or reuse the value.
> All ports bind to 127.0.0.1.

ChatGPT and public MCP endpoints are out of scope.

## Prerequisites

- [asdf](https://asdf-vm.com/) with the tools in `.tool-versions` (Python,
  uv, task): `asdf install`
- Docker with Compose (Docker Desktop or similar), about 6 GB of free RAM
- `openssl` (used by `task setup` to generate secrets)

## Quickstart

```bash
task setup        # uv sync, create .env with random secrets, build the dbt image
task up           # Postgres, ClickHouse, migrations and the web app, waits for health
task seed         # POST sample good and bad submissions
task el           # dlt: Postgres submissions -> ClickHouse raw
task dbt:build    # seeds, models and tests (staging, marts)
task dashboard    # dbt Charts; opens the overview board
task mcp:claude   # build dbt-mcp and print the Claude Code and Desktop setup
task e2e          # isolated end-to-end suite (own project, volumes and ports)
```

Then open the form (`task app:open`), submit a few messages, and rerun
`task el && task dbt:build`. For Claude Code, run `claude` from the repo root,
approve the `dbt` server and ask "what are the top browsers?". `task mcp:smoke`
does the same without a GUI.

`task --list` shows everything else. `task down` stops the stack and keeps
data. `task reset` also deletes the volumes and the dbt artifacts in
`transform/dbt/target`.

## Ports (127.0.0.1 only)

| Port | Service | Task |
|---|---|---|
| 8000 | Web form | `task up` |
| 5432 | Postgres | `task up` |
| 8123 / 9000 | ClickHouse HTTP / native | `task up` |
| 8090 | dbt Charts (`/overview/`, `/words/`) | `task dashboard` |
| 8081 | dbt docs | `task dbt:docs` |

The e2e project uses 15432, 18123, 19000, 18000, 18090, 18088 and 18081.

## Docs

- [docs/architecture.md](docs/architecture.md): diagram, components, data flow
- [docs/pii.md](docs/pii.md): what is stored and where
- [docs/grants-matrix.md](docs/grants-matrix.md): who can read what
- [docs/agent-guide.md](docs/agent-guide.md): how agents should query the marts
- [mcp/README.md](mcp/README.md): Claude Code and Desktop setup
- [dashboard/charts/README.md](dashboard/charts/README.md): the dbt Charts boards
- [docs/test-strategy.md](docs/test-strategy.md): test pyramid, gates, e2e map
- [docs/debugging.md](docs/debugging.md): per-hop debugging and known failure modes
- [plan.md](plan.md) and [spec.md](spec.md): plan and requirements
