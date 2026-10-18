# Debugging guide

Work from the data towards the user: web, EL, dbt, charts, Superset, MCP.
`task ps` lists containers, `task logs SVC=<service>` follows logs,
`task sh SVC=<service>` opens a shell, `task psql` and `task ch` open admin
clients (`task ch -- -q 'select 1'`).

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
  `EL_MAX_ATTEMPTS` failed attempts.
- Loads and state (as `default`, via `task ch`):

```sql
SELECT load_id, status, inserted_at FROM raw._dlt_loads ORDER BY inserted_at DESC LIMIT 5;
SELECT count(), uniqExact(id) FROM raw.submissions;
SELECT table FROM (SELECT name AS table FROM system.tables WHERE database = 'raw');
```

- `count()` above `uniqExact(id)` is normal between merges only if a run
  failed midway. Rerun `task el`.
- dlt writes merge staging tables as `raw.stg___*` in the same database.

### dbt

- Run `task dbt:debug` first (profile and connection).
- Artifacts are on the host: `transform/dbt/target/run_results.json`,
  `transform/dbt/logs/dbt.log`.
- Narrow a failure: `task dbt:build -- --select stg_app__submissions+`.
- Freshness warns only: `task dbt:freshness`.
- Missing descriptions: `task dbt:coverage`.

### Charts (dbt Charts)

```bash
task logs SVC=charts
docker compose --profile core --profile dashboard exec -w /work/project charts dct doctor
docker compose --profile core --profile dashboard exec -w /work/project charts \
  dct query warehouse 'select * from marts.mart_browser_distribution'
task charts:validate     # dct validate --warehouse on every board
task charts:render       # HTML under dashboard/charts/renders
```

If boards are empty, rerun `task dbt:parse TARGET=charts TARGET_PATH=target/charts`
(the manifest) and `task dashboard`.

### Superset

- `task logs SVC=superset-init` (provisioning) and `task logs SVC=superset`.
- Login at http://127.0.0.1:8088 as `admin` with `SUPERSET_ADMIN_PASSWORD`
  from `.env`. The word cloud is at `/superset/dashboard/word-cloud/`.
  Anonymous visitors are redirected to the login page by design.
- Reprovision after changing the bundle: `docker compose --profile core
  --profile dashboard up -d --build superset-init superset`.
- First start takes about a minute (`db upgrade`, `superset init`).

### MCP

- Build first, because stdout is the JSON-RPC stream: `task mcp:build`.
- No GUI check: `task mcp:smoke` lists the 6 tools and asks for top browsers.
- Verbose server log on stderr: set `DBT_MCP_LOG_LEVEL=DEBUG` in `.env`.
- What Claude actually ran, queried as admin:

```sql
SYSTEM FLUSH LOGS;
SELECT event_time, query_kind, written_rows, substring(query, 1, 120)
FROM system.query_log
WHERE user = 'mcp_reader' AND type = 'QueryFinish'
ORDER BY event_time DESC LIMIT 20;
```

Everything should be `Select` with `written_rows = 0` (ClickHouse also
logs an `Exists` kind from the connection check).

Harmless stderr noise in `task mcp:smoke`: `Could not resolve credentials ...
DBT_HOST` (no dbt platform, by design) and `Failed to open log file for append:
Read-only file system` (the project mount is read-only, logs go to stderr).

## E2E

- `E2E_KEEP=1 task e2e` leaves project `aictx-e2e` running on ports 15432
  (Postgres), 18123 (ClickHouse), 18000 (web), 18090 (charts), 18088 (Superset).
- Inspect it: `docker compose -p aictx-e2e ps` and
  `docker compose -p aictx-e2e logs <service>`.
- Admin passwords are in `scripts/e2e/e2e.env`.
- Clean up with `docker compose -p aictx-e2e --profile '*' down -v`.
- One test: `E2E_KEEP=1 task e2e` once, then
  `uv run pytest -m e2e scripts/e2e/tests/test_03_submissions.py -k csrf`.
  Stages depend on earlier ones, so a lone later stage may need the earlier ones.

## Failure modes seen in this repo

| Symptom | Cause | Fix |
|---|---|---|
| Host or sibling containers cannot reach ClickHouse, connection reset | The image listens on localhost only | `infra/clickhouse/config.d/listen.xml` sets `listen_host` to `0.0.0.0` (the host side is still bound to 127.0.0.1) |
| e2e stack uses dev passwords, or dev data shows up in e2e | `task` loads the dev `.env` | The `E2E_COMPOSE` var runs through `env $(...)` so `scripts/e2e/e2e.env` wins. Never run raw `docker compose -p aictx-e2e` without `--env-file` |
| ClickHouse users missing or stale in e2e | `users.d` is bind-mounted and the entrypoint writes into it | `task e2e` copies `infra/clickhouse/users.d` into `scripts/e2e/.work/users.d` and refreshes it in place (recreating it races the mount) |
| Grants or users changed in init scripts have no effect | Init scripts run on an empty volume only | `task reset` |
| Reader query fails with a constraint error, or `SETTINGS max_execution_time=...` is refused | `readonly=2` users may change settings, so the `reader` profile locks them: `max_execution_time` at most 30, `max_result_rows` at most 10000, `max_memory_usage` at most 1G | Expected. Lower the value or add a `LIMIT`, never raise it. A client that sends `max_execution_time` above 30 (for example from its own config) is denied. dbt Charts sets it to 30 itself |
| `ACCESS_DENIED` on `system.*` or `information_schema` | The grant gates are on for every user without an explicit grant | Query it as admin (`task ch`). `el_loader` needs `SELECT` on `INFORMATION_SCHEMA.COLUMNS` for dlt |
| `dbt show` fails with a double `LIMIT` | `dbt show` appends its own limit and ClickHouse rejects two | No `LIMIT` in the SQL, use `--limit N`. dbt-mcp also drops its cap if the word "limit" appears anywhere in the SQL |
| `dbt show --select stg_...` is denied for `mcp_reader` | It re-runs the model SQL, which reads staging | By design. Use `show --inline` over `{{ ref('mart_...') }}` |
| `task seed` returns 429 on a second run | The rate limit counts failed passwords per client network (5 per 15 min), and `seed` posts bad ones on purpose. Under Docker NAT all clients share one network | Wait, `task reset`, or raise `RATE_LIMIT_MAX` in `.env` and restart `web` |
| `service "clickhouse" depends on undefined service "..."` compose errors | A profile is missing: services depend on `core` | Use `--profile core --profile mcp` (and `--profile core --profile dbt`, `--profile core --profile dashboard`). `.mcp.json` already does |
| Claude reports a broken MCP server, garbage on stdout | Image still building, or compose printed to stdout | `task mcp:build` first, keep `-i --no-TTY` |
| `task e2e` flakes at the very start with connection errors | ClickHouse runs a temporary server during init, so the healthcheck can pass early | The session fixture in `scripts/e2e/conftest.py` waits for both stores |
| Superset shows the login page for the word cloud | Anonymous access is off on purpose | Log in as `admin` |
| `task lint` fails on `superset:lock` | The lock is checked inside the Superset image with its Python 3.10 | See `dashboard/superset/README.md` for the re-lock command |
| dbt v2 fails on docs with a `;` in a description | v2 docs persistence breaks on it | Remove the semicolon (the description coverage check does not catch this) |

## Useful SQL

```sql
-- latest dlt loads
SELECT * FROM raw._dlt_loads ORDER BY inserted_at DESC LIMIT 5;
-- who ran what in the last 10 minutes
SELECT user, query_kind, count() FROM system.query_log
WHERE event_time > now() - 600 AND type = 'QueryFinish' GROUP BY 1, 2;
-- failed queries (denials)
SELECT user, exception_code, substring(exception, 1, 100) FROM system.query_log
WHERE type LIKE 'Exception%' ORDER BY event_time DESC LIMIT 10;
-- table sizes
SELECT database, name, total_rows FROM system.tables
WHERE database IN ('raw', 'staging', 'marts');
```
