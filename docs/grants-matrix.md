# Grants matrix

Least privilege for every service. Created by `infra/postgres/init/02-roles.sh`,
the Alembic migration `apps/web/migrations/versions/0001_create_app_schema.py`
and `infra/snowflake/setup.sql`. Every cell is asserted by
`scripts/e2e/tests/test_02_access.py`.

Postgres init scripts run only on the first start of an empty volume. To
re-apply after changing them, run `task reset`. The Snowflake script is
idempotent: run `task snowflake:setup` again.

## Postgres (database `app`, schema `app`)

| Role | Login | Schema `app` | `submissions` | `request_metadata` | `auth_attempts` |
|---|---|---|---|---|---|
| `postgres` | admin | all | all | all | all |
| `app_owner` | yes | owner (runs Alembic) | owner | owner | owner |
| `web_writer` | yes | USAGE | INSERT, SELECT (`id`) | INSERT | INSERT, SELECT |
| `el_reader` | yes | USAGE | SELECT | none | none |

Other details:
- `PUBLIC` has no `CONNECT` on `app` or `postgres`, and no rights on schema
  `public`.
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
| connect to database `postgres` | `web_writer` | denied |

## Snowflake (database `AICTX`)

One role per user, same names with an `AICTX_` prefix on the role. Grants are on
schemas, not tables. dbt rebuilds tables with `CREATE OR REPLACE`, which drops
grants on the old object, so readers get `FUTURE` grants on `MARTS`. dbt v2 has
no `grants:` support, so schema-level grants are also the only option.

| User (role) | `RAW` | `RAW_STAGING` | `STAGING` | `MARTS` | Warehouse |
|---|---|---|---|---|---|
| `EL_LOADER` (`AICTX_EL_LOADER`) | all privileges | all privileges | none | none | `AICTX_LOAD_WH` |
| `DBT_RUNNER` (`AICTX_DBT_RUNNER`) | USAGE, SELECT on all and future tables | none | all privileges | all privileges | `AICTX_TRANSFORM_WH` |
| `MCP_READER` (`AICTX_MCP_READER`) | none | none | none | USAGE, SELECT on all and future tables and views | `AICTX_READ_WH` |
| `CHARTS_READER` (`AICTX_CHARTS_READER`) | none | none | none | same as `MCP_READER` | `AICTX_READ_WH` |

All four have `USAGE` on the database. The script grants nothing to `PUBLIC`,
and none of the four can read `SNOWFLAKE.ACCOUNT_USAGE`.

Notes:
- dlt merges through `RAW_STAGING`, so `EL_LOADER` owns two schemas. `ALL
  PRIVILEGES` covers `CREATE TABLE` and `ALTER ... ADD COLUMN` (dlt schema
  evolution) and `DELETE` (merge).
- `DBT_RUNNER` cannot write to `RAW`, and cannot see `RAW_STAGING`.
- Readers see only `MARTS` in `INFORMATION_SCHEMA`, so the catalog leaks no
  other table name.
- The dbt platform production job connects as `DBT_RUNNER`. The Semantic Layer
  credential is `MCP_READER`, so metric queries get the same limits as `show`.
- The shared `AICTX_MONITOR` resource monitor (10 credits a month, notify at
  80 percent, suspend at 100) is attached to all three warehouses.

### What bounds a reader

Snowflake has no `readonly` flag, row cap or memory cap, which the ClickHouse
version of this repo had. Readers are read-only through grants alone, and
bounded by:

| Limit | Where | Value |
|---|---|---|
| Statement timeout | user `MCP_READER`, user `CHARTS_READER`, warehouse `AICTX_READ_WH` | 30 s |
| Credits | resource monitor `AICTX_MONITOR` | 10 a month |

A session may ask for a longer timeout (`ALTER SESSION SET
STATEMENT_TIMEOUT_IN_SECONDS = 600`), but the user and warehouse cap wins: a 45 s
query is still cancelled at 30 s. An e2e test pins this.

Denials come in two forms, both a `ProgrammingError` in Python:

| Code | Meaning | Example |
|---|---|---|
| `002003` | "does not exist or not authorized": the object is invisible | a reader selecting `RAW.SUBMISSIONS` |
| `003001` | "insufficient privileges": the object is visible but not writable | a reader running `INSERT INTO MARTS.<t>` |

Examples:

| Statement | As | Result |
|---|---|---|
| `SELECT ... FROM MARTS.<table>` | `MCP_READER`, `CHARTS_READER` | allowed |
| `INSERT`, `DELETE`, `TRUNCATE`, `ALTER`, `DROP` on a mart | any reader | denied |
| `CREATE TABLE MARTS.<t>`, `CREATE SCHEMA` | any reader | denied |
| `SELECT ... FROM RAW.<t>`, `STAGING.<t>` | any reader | denied |
| `SELECT ... FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | any reader | denied |
| `SELECT ... FROM MARTS.<t>` after dbt rebuilt it | any reader | allowed (`FUTURE` grant) |
| `CREATE TABLE RAW.<t>`, `INSERT`, `ALTER ... ADD COLUMN`, `DELETE` | `EL_LOADER` | allowed |
| `CREATE TABLE MARTS.<t>` or `STAGING.<t>` | `EL_LOADER` | denied |
| `SELECT ... FROM MARTS.<t>` | `EL_LOADER` | denied |
| `CREATE VIEW` or `CREATE TABLE` in `STAGING` and `MARTS` | `DBT_RUNNER` | allowed |
| `ALTER TABLE MARTS.<a> SWAP WITH MARTS.<b>` | `DBT_RUNNER` | allowed |
| `INSERT`, `CREATE TABLE`, `DROP`, `ALTER` on `RAW` | `DBT_RUNNER` | denied |
| `CREATE SCHEMA`, `CREATE DATABASE` | `EL_LOADER`, `DBT_RUNNER` | denied |

### The dbt platform token

`DBT_TOKEN` is a service token with the permission sets Semantic Layer Only and
Metadata Only. It can query every metric but cannot run jobs or read the
warehouse directly. It sits in `.env` and the dbt-mcp container, so treat it
like a password. See [semantic-layer.md](semantic-layer.md).
