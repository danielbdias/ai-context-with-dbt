# End-to-end harness

A pytest suite run from the host against an isolated compose project
(`-p aictx-e2e`, fresh volumes, host ports 15432/18000/18090/18081), so it can
run next to the dev stack. Postgres and the web app run in that project.

The warehouse is **Snowflake, your real account**. Snowflake cannot run in a
container, so each run creates its own database, `AICTX_E2E_<8 hex>`, by running
`infra/snowflake/setup.sql` with that name, and drops it afterwards, also when
tests fail. The dev database `AICTX` is never touched: the name is passed to
every container and connection, and the drop refuses `AICTX`.

## Run

```bash
export SNOWFLAKE_ADMIN_USER=...       # the account admin that ran task snowflake:setup
export SNOWFLAKE_ADMIN_PASSWORD=...
task e2e                              # up, pytest, always down -v and drop the database
E2E_KEEP=1 task e2e                   # keep the stack and the database to debug
E2E_DATABASE=AICTX_E2E_AB12CD34 ...   # reuse a kept database
task e2e:clean                        # drop AICTX_E2E_* databases left by a killed run
```

It needs `SNOWFLAKE_ACCOUNT` and the four service passwords from `.env` (the task
loads them), plus the admin credentials above, because creating a database and
granting on it needs `ACCOUNTADMIN`. Without them the Snowflake stages skip and
the Postgres stages still run.

`e2e.env` holds the throwaway Postgres and web values and the ports. The suite is
marked `e2e` and is excluded from `task test`. A run costs a few warehouse
credits (XS warehouses, 60 s auto-suspend) and takes several minutes.

## Stages

| File | Covers |
|---|---|
| `test_01_health.py` | Postgres and web healthy, migrations applied |
| `test_02_access.py` | Postgres grants. Snowflake grants: schemas and users exist, readers read `MARTS` only and see nothing else in the catalog, no writes, `FUTURE` grants survive a dbt rebuild, the 30 s timeout holds even if a session asks for 600 s, `el_loader` and `dbt_runner` can do exactly their jobs |
| `test_03_submissions.py` | Web app writes and rejections |
| `test_04_el.py` | dlt: idempotent reruns, soft delete, no aux tables, fails when Snowflake is unreachable |
| `test_05_dbt.py` | dbt v2 build and docs generate, a stale deleted duplicate cannot win the dedup, mart counts and word frequencies vs Postgres, readers can read the built marts |
| `test_06_mcp.py` | dbt-mcp over stdio: exactly 12 tools, `show` answers top browsers, Snowflake query history shows only `MCP_READER` reads; `dbt show --inline --target mcp` returns rows, `show --select` on staging is denied |
| `test_07_dashboards.py` | dbt Charts renders both boards (HTML has the expected numbers and labels), `dct validate --warehouse` passes, `/` `/overview/` `/words/` 200, `charts_reader` is limited to `MARTS` |

Not covered here: the Semantic Layer. The dbt platform serves it from the dev
database, so `task mcp:smoke` checks it against that.

What the ClickHouse suite asserted and Snowflake cannot: `readonly=2`, per-query
row and memory caps, and `system.*` introspection. Readers are read-only through
grants alone, and a statement timeout and a resource monitor bound them.

## Helpers (`helpers.py`)

- `sf_query(sql, user="dbt_runner", params=None)`: runs in the per-run database.
  Users are `el_loader`, `dbt_runner`, `mcp_reader`, `charts_reader` and `admin`.
  Denials raise `DENIED` (`ProgrammingError`). `dbt_runner` is the default
  because it can read `RAW`, `STAGING` and `MARTS`.
- `sf_connect(user)`: a raw connection, for session-level tests.
- `E2E_DATABASE`: this run's database name.
- `run_dbt(*args)` runs the dbt one-shot (artifacts in `target/e2e`).
  `run_el(env=None)` builds and runs the EL one-shot (profile `el` is not in
  `E2E_PROFILES`: `up --wait` must not start a one-shot).
- `pg_query`, `pg_query_as(user, password, sql)`, `migrate(rev, direction=)`,
  `compose_run(service, ..., profiles=[...])`, `web_client()`.

## Add a stage

1. Add `scripts/e2e/tests/test_NN_<name>.py` (files run in name order).
2. For Snowflake, add `pytestmark = pytest.mark.usefixtures("e2e_database")` (or
   take `e2e_database` as a fixture) so the database exists first.
3. Add the new profile(s) to `E2E_PROFILES` in `Taskfile.yml`, and any new
   variables to `e2e.env`.
