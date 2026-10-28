# Debugging guide

Work from the data towards the user: web, EL, dbt, charts, MCP, Semantic Layer.
`task ps` lists containers, `task logs SVC=<service>` follows logs,
`task sh SVC=<service>` opens a shell, `task psql` opens an admin Postgres
client and `task sf -- -q '<sql>'` runs Snowflake SQL as `DBT_RUNNER`
(`task sf -- -q 'select current_role()'`).

## Per-hop guide

### web

- Logs: `task logs SVC=web`. JSON lines with a request id, never message bodies.
- Health: `curl -s http://127.0.0.1:8000/healthz`.
- Did the write happen?

```bash
task psql -- -c "select count(*) from app.submissions"
task psql -- -c "select reason, success, count(*) from app.auth_attempts group by 1, 2"
```

- `auth_attempts.reason` tells why a post was refused: `bad_password`,
  `rate_limited`, `csrf`, `invalid_input`.

### EL (dlt)

- Output: the load info printed by `task el`. Exit code is non-zero after
  `EL_MAX_ATTEMPTS` failed attempts. A wrong account name takes about 20 s to
  fail, because the connector retries.
- Loads and state (`DBT_RUNNER` can read `RAW`):

```bash
task sf -- -q "select load_id, status, inserted_at from raw._dlt_loads order by inserted_at desc limit 5"
task sf -- -q "select count(*), count(distinct id) from raw.submissions"
task sf -- -q "select table_name from information_schema.tables where table_schema = 'RAW'"
```

- `count(*)` above `count(distinct id)` is normal only if a run failed midway.
  Rerun `task el`.
- dlt writes merge staging tables in `RAW_STAGING`. `DBT_RUNNER` cannot see that
  schema. Use `EL_LOADER` or an admin.
- No rows from `task el`? Postgres may be empty: `task seed` and
  `task seed:history`.

### dbt

- Run `task dbt:debug` first (profile and connection).
- Artifacts are on the host: `transform/dbt/target/run_results.json`,
  `transform/dbt/logs/dbt.log`.
- Narrow a failure: `task dbt:build -- --select stg_app__submissions+`.
- Freshness warns only: `task dbt:freshness`.
- Missing descriptions on models, columns, metrics, saved queries and
  dimensions: `task dbt:coverage`.
- Check the metric definitions without the platform: parse, then validate
  `target/semantic_manifest.json` with `dbt-semantic-interfaces` (see
  `docs/semantic-layer.md`). Local `dbt parse` skips semantic validation.

### Charts (dbt Charts)

```bash
task logs SVC=charts
docker compose --profile core --profile dashboard exec -w /work/project charts \
  dct query warehouse 'select * from AICTX.MARTS.mart_browser_distribution'
task charts:validate     # dct validate --warehouse on every board
task charts:render       # HTML under dashboard/charts/renders
```

If boards are empty, rerun `task dbt:parse TARGET=charts TARGET_PATH=target/charts`
(the manifest) and `task dashboard`. Use fully qualified names in `dct query`.

### MCP

- Build first, because stdout is the JSON-RPC stream: `task mcp:build`.
- No GUI check: `task mcp:smoke` lists the 12 tools, asks for top browsers, and
  compares a metric with `count(*)`. It needs the dbt platform variables.
- Verbose server log on stderr: set `DBT_MCP_LOG_LEVEL=DEBUG` in `.env`.
- What Claude actually ran, as an admin (the table function is near real time,
  the `ACCOUNT_USAGE` view is up to 45 minutes late):

```sql
SELECT start_time, query_type, error_code, LEFT(query_text, 120)
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(USER_NAME => 'MCP_READER'))
ORDER BY start_time DESC LIMIT 20;
```

Everything should be a `SELECT` (plus `ALTER_SESSION` and `SHOW`/`DESCRIBE`
setup). `DBT_RUNNER` only sees its own queries, so `task sf` cannot answer this.

Harmless stderr noise in `task mcp:smoke`: `Failed to open log file for append:
Read-only file system` (the project mount is read-only, logs go to stderr) and
`Timeout waiting for LSP server to connect` on shutdown.

### Semantic Layer

| Symptom | Check |
|---|---|
| Metric tools say `DBT_HOST is a required environment variable` | `DBT_HOST`, `DBT_TOKEN` or `DBT_PROD_ENV_ID` is missing in `.env` |
| `Name or service not known` or `name resolver error: produced zero addresses` | Set `DBT_HOST_PREFIX` to the first label of `DBT_HOST` |
| `403` | The token lacks Semantic Layer Only and Metadata Only, or the account restricts IP addresses |
| `list_metrics` is empty or metrics are stale | The production job has not run since the change, or it ran on the wrong branch |
| Numbers disagree with `show` | The job has not rebuilt since `task el`. Run it |

## E2E

- `E2E_KEEP=1 task e2e` leaves project `aictx-e2e` running on ports 15432
  (Postgres), 18000 (web), 18090 (charts) and 18081 (dbt docs), and keeps the
  per-run Snowflake database. The database name is printed at the end.
- Inspect it: `docker compose -p aictx-e2e ps` and
  `docker compose -p aictx-e2e logs <service>`.
- Reuse the database: `E2E_DATABASE=AICTX_E2E_<id> uv run pytest -m e2e scripts/e2e/tests/test_05_dbt.py`.
- Clean up with `docker compose -p aictx-e2e --profile '*' down -v` and
  `task e2e:clean` for databases left by a killed run.
- Postgres passwords are in `scripts/e2e/e2e.env`.
- Stages depend on earlier ones, so a lone later stage may need the earlier ones.

## Failure modes seen in this repo

| Symptom | Cause | Fix |
|---|---|---|
| `connection to server at "127.0.0.1", port 5432` reaches the wrong database | Another Postgres on the host (for example Homebrew) is bound to 5432 and shadows the container's published port. It may even accept the demo's admin password | Set `POSTGRES_PORT` in `.env` to a free port, or run client tools inside the container (`task psql`, `task seed:history` do) |
| `task up` or `docker compose` complains about `SNOWFLAKE_ACCOUNT` | `.env` has it empty | Set it to `orgname-accountname`. `task el` and the dbt tasks check it first |
| dbt-mcp exits at start with `DBT_PROD_ENV_ID ... int_parsing` | An empty `DBT_PROD_ENV_ID` reached dbt-mcp, which parses it as an integer | `transform/mcp-entrypoint.sh` unsets empty `DBT_*` variables. Rebuild the image (`task mcp:build`) |
| Platform job fails with `unexpected '('` in `metricflow_time_spine.sql` | The job built `main`, which still has the ClickHouse SQL | Merge the Snowflake migration, or set the environment's custom branch |
| Models land in `staging_marts` or the readers see nothing | The job's target name is not `prod`, so `generate_schema_name` prefixed the schema | Set **Target name** `prod` on the platform job |
| `dct validate --warehouse` exits 137 with no output | The charts container hit its memory limit. `dct serve` grows to about 400 MB and `validate` starts a second process | Compose gives `charts` 1 GB. Do not lower it |
| Reader query fails with `002003` (does not exist or not authorized) | The object is not in `MARTS`, or it is, and a grant is missing | Expected for `RAW` and `STAGING`. For a mart, rerun `task snowflake:setup` |
| Reader query is cancelled after 30 s | The user and warehouse statement timeout. A session cannot raise it | Expected. Narrow the query |
| `CREATE OR REPLACE` made a mart unreadable | A grant was on the table, not a `FUTURE` grant | Rerun `task snowflake:setup`, which grants on future tables |
| A date looks one day off | `TIMESTAMP_LTZ` follows the session time zone | Pin it: `convert_timezone('UTC', col)::date` |
| `dbt show` fails with a double `LIMIT` | `dbt show` appends its own limit | No `LIMIT` in the SQL, use `--limit N`. dbt-mcp also drops its cap if the word "limit" appears anywhere in the SQL |
| `dbt show --select stg_...` is denied for `MCP_READER` | It re-runs the model SQL, which reads `RAW` and `STAGING` | By design. Use `show --inline` over `{{ ref('mart_...') }}` |
| e2e stack uses dev passwords, or dev data shows up in e2e | `task` loads the dev `.env` | The `E2E_COMPOSE` var runs through `env $(...)` so `scripts/e2e/e2e.env` wins. Never run raw `docker compose -p aictx-e2e` without `--env-file` |
| `task e2e` stops at once | It needs `SNOWFLAKE_ADMIN_USER` and `SNOWFLAKE_ADMIN_PASSWORD` to create a database | Export them, then rerun |
| Leftover `AICTX_E2E_*` databases | A run was killed before its teardown | `task e2e:clean` |
| Init script changes have no effect | Postgres init scripts run on an empty volume only | `task reset`. The Snowflake script is rerunnable instead |
| `task seed` returns 429 on a second run | The rate limit counts failed passwords per client network (5 per 15 min), and `seed` posts bad ones on purpose. Under Docker NAT all clients share one network | Wait, `task reset`, or raise `RATE_LIMIT_MAX` in `.env` and restart `web` |
| Claude reports a broken MCP server, garbage on stdout | Image still building, or compose printed to stdout | `task mcp:build` first, keep `-i --no-TTY` |
| dbt v2 fails on docs with a `;` in a description | v2 docs persistence breaks on it | Remove the semicolon (`task dbt:coverage` catches it) |

## Useful SQL

Run with `task sf -- -q '...'`, or as an admin for the account-wide ones.

```sql
-- latest dlt loads
SELECT * FROM RAW._DLT_LOADS ORDER BY INSERTED_AT DESC LIMIT 5;
-- table sizes in the demo schemas
SELECT table_schema, table_name, row_count FROM AICTX.INFORMATION_SCHEMA.TABLES
WHERE table_schema IN ('RAW', 'STAGING', 'MARTS') ORDER BY 1, 2;
-- failed queries (denials), as an admin
SELECT user_name, error_code, LEFT(error_message, 100)
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(RESULT_LIMIT => 1000))
WHERE error_code IS NOT NULL ORDER BY start_time DESC LIMIT 10;
-- credits used by the demo warehouses, as an admin
SELECT warehouse_name, SUM(credits_used) FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE warehouse_name LIKE 'AICTX_%' AND start_time > DATEADD(day, -7, CURRENT_TIMESTAMP)
GROUP BY 1;
```
