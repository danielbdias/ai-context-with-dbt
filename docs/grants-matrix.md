# Grants matrix

Least privilege for every service. Created by `infra/postgres/init/02-roles.sh`,
the Alembic migration `apps/web/migrations/versions/0001_create_app_schema.py`
and `infra/clickhouse/init/01-access.sh`. Every cell is asserted by
`scripts/e2e/tests/test_02_access.py`.

Init scripts run only on the first start of an empty volume. To re-apply after
changing them, run `task reset`.

## Postgres (database `app`, schema `app`)

| Role | Login | Schema `app` | `submissions` | `request_metadata` | `auth_attempts` |
|---|---|---|---|---|---|
| `postgres` | admin | all | all | all | all |
| `app_owner` | yes | owner (runs Alembic) | owner | owner | owner |
| `web_writer` | yes | USAGE | INSERT, SELECT (`id`) | INSERT | INSERT, SELECT |
| `el_reader` | yes | USAGE | SELECT | none | none |
| `superset_meta` | yes | none | none | none | none |

Other details:
- `superset_meta` owns database `superset` and connects only to it. The other
  roles cannot connect to `superset`. `PUBLIC` has no `CONNECT` on `app`,
  `superset` or `postgres`, and no rights on schema `public`.
- `web_writer` has USAGE on both identity sequences. `SELECT (id)` is
  required by `INSERT ... RETURNING id` and exposes no message text. The app
  inserts `auth_attempts` after `submissions` in the same transaction, so no
  UPDATE is needed.
- Foreign-key checks run as the table owner, so `web_writer` needs no
  REFERENCES or SELECT on the parent table.

Examples:

| Statement | As | Result |
|---|---|---|
| `INSERT INTO app.submissions (...) RETURNING id` | `web_writer` | allowed |
| `SELECT message FROM app.submissions` | `web_writer` | denied |
| `SELECT * FROM app.request_metadata` | `web_writer` | denied |
| `UPDATE app.submissions ...` | `web_writer` | denied |
| `SELECT * FROM app.submissions` | `el_reader` | allowed |
| `SELECT * FROM app.request_metadata` | `el_reader` | denied |
| `SELECT * FROM app.auth_attempts` | `el_reader` | denied |
| connect to database `superset` | `web_writer` | denied |

## ClickHouse

Grants are at database level (`ON marts.*`) so they survive dbt rebuilds. dbt
v2 has no `grants:` support, so this is also the only option.
`select_from_system_db_requires_grant` and
`select_from_information_schema_requires_grant` are on (`config.d`).

| User | raw | raw_staging | staging | marts | system tables |
|---|---|---|---|---|---|
| `default` | admin | admin | admin | admin | all (init and tests only) |
| `el_loader` | CREATE TABLE, DROP TABLE, INSERT, SELECT, ALTER, TRUNCATE | same | none | none | SELECT `tables`, `columns`, `databases`, `INFORMATION_SCHEMA.COLUMNS` |
| `dbt_runner` | SELECT | none | CREATE TABLE/VIEW, DROP TABLE/VIEW, INSERT, SELECT, ALTER, TRUNCATE | same as staging | SELECT `tables`, `columns`, `databases`, `settings`, `functions` |
| `mcp_reader` | none | none | none | SELECT | none |
| `charts_reader` | none | none | none | SELECT | none |
| `superset_reader` | none | none | none | SELECT on `marts.mart_word_frequencies` only | none |

Notes:
- `ALTER` for `el_loader` covers `ADD COLUMN` (dlt schema evolution) and
  `ALTER DELETE/UPDATE` (merge).
- `dbt_runner` can run `EXCHANGE TABLES` in `staging` and `marts` with the
  grants above.
- dlt's ClickHouse destination uses ONE database per pipeline, so it puts
  merge staging tables next to the final table: `raw.submissions` plus
  `raw.stg___submissions` (and its own `raw.stg____dlt_version`,
  `raw.stg___dlt_sentinel_table`). `raw_staging` stays created and granted but
  dlt does not use it. Merge runs `DELETE FROM raw.submissions WHERE id IN
  (...)` (lightweight delete, synchronous by default), covered by `ALTER`.
- `system.tables` and `system.columns` only list objects the user can see, so
  `dbt_runner` and `el_loader` never see `request_metadata` or `auth_attempts`
  (those never reach ClickHouse).
- The table-level grant for `superset_reader` is accepted before the table
  exists and survives drop and recreate.
- Not granted yet, to be proven by spikes: `information_schema.*` and
  `CREATE DATABASE` for dbt, and `system.tables`/`system.columns` for readers
  (M7 and M8). Add them to `01-access.sh` only when a spike shows they are
  needed.

### Settings profile `reader` (`mcp_reader`, `charts_reader`, `superset_reader`)

| Setting | Value | Constraint |
|---|---|---|
| `readonly` | 2 | (no setting can be changed to 0) |
| `max_execution_time` | 30 | MIN 1, MAX 30 |
| `max_result_rows` | 10000 | MIN 1, MAX 10000 |
| `max_memory_usage` | 1000000000 | MIN 1, MAX 1000000000 |
| `result_overflow_mode` | `throw` | CONST |

`MIN 1` matters because 0 means unlimited and would satisfy a bare `MAX`.

Examples:

| Statement | As | Result |
|---|---|---|
| `SELECT ... FROM marts.<table>` | `mcp_reader`, `charts_reader` | allowed |
| `SELECT ... FROM marts.mart_word_frequencies` | `superset_reader` | allowed |
| `SELECT ... FROM marts.<other table>` | `superset_reader` | denied |
| `INSERT INTO marts.<table> ...` | any reader | denied |
| `SELECT ... FROM raw.<table>` or `staging.<table>` | any reader | denied |
| `SELECT ... FROM system.query_log` | any reader | denied |
| `... SETTINGS max_result_rows = 0` | any reader | denied (constraint) |
| `... SETTINGS max_execution_time = 600` | any reader | denied (constraint) |
| `... SETTINGS result_overflow_mode = 'break'` | any reader | denied (constraint) |
| `SELECT number FROM numbers(20000)` | any reader | denied (row limit) |
| `CREATE TABLE raw.<t> ...` | `el_loader` | allowed |
| `CREATE TABLE marts.<t> ...` | `el_loader` | denied |
| `CREATE TABLE marts.<t> ...` | `dbt_runner` | allowed |
| `INSERT INTO raw.<t> ...` | `dbt_runner` | denied |
