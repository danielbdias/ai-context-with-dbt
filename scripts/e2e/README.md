# End-to-end harness

A pytest suite run from the host against an isolated compose project
(`-p aictx-e2e`, fresh volumes, host ports 15432/18123/19000/...), so it can run
next to the dev stack.

## Run

```bash
task e2e                              # up, wait healthy, pytest, always down -v
E2E_KEEP=1 task e2e                   # leave the stack up to debug
task e2e E2E_PROFILES=core,app,el    # extra compose profiles (default core,app)
```

`e2e.env` holds test-only credentials and ports. It replaces `.env` for this
project. The suite is marked `e2e` and is excluded from `task test`.

## Stages

| File | Covers |
|---|---|
| `test_01_health.py` | Stack healthy |
| `test_02_access.py` | Grants matrix |
| `test_03_submissions.py` | Web app writes and rejections |
| `test_04_el.py` | dlt: idempotent reruns, soft delete, no aux tables, fails when ClickHouse is down |
| `test_05_dbt.py` | dbt v2 build and docs generate, mart counts and word frequencies vs Postgres |
| `test_06_mcp.py` | dbt-mcp over stdio: exactly 6 tools, `show` answers top browsers, `query_log` shows only `mcp_reader` reads; `dbt show --inline --target mcp` returns rows, `show --select` on staging is denied |

`run_dbt(*args)` does the same for the dbt one-shot (profile `dbt`, artifacts in
`target/e2e`). `run_el(env=None)` builds and runs the EL one-shot (profile `el` is not in
`E2E_PROFILES`: `up --wait` must not start a one-shot) and returns the process.

## Add a stage

1. Add `scripts/e2e/tests/test_NN_<name>.py` (files run in name order).
2. Use the helpers in `scripts/e2e/helpers.py`:
   `pg_query`, `pg_query_as(user, password, sql)`, `migrate(rev, direction=)`,
   `ch_command` (DDL/INSERT), `ch_query(sql, user=, password=)` (raises on denied/constraint
   errors), `compose_run(service, ..., profiles=[...])` for one-shot services,
   `web_client()` for the web app.
3. Add the new profile(s) to `E2E_PROFILES` in `Taskfile.yml`, and any new
   variables to `e2e.env`.
