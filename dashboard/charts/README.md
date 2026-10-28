# dbt Charts (`dct`)

Boards are YAML files in `charts/`. `dct serve` renders each one at
`/<file name>/`: `/overview/` and `/words/`. The warehouse is the dbt profile
`aictx`, target `charts`, which connects to Snowflake as `CHARTS_READER` (role
`AICTX_CHARTS_READER`, `SELECT` on `MARTS` only).

## Layout

| Path | What |
|---|---|
| `dbt_charts.yml` | The `warehouse` source (`type: dbt_profile`, profile `aictx`, target `charts`) and server settings |
| `charts/overview.yml` | KPI, two donuts, daily line, top browser×OS table |
| `charts/words.yml` | Top 30 words bar |
| `entrypoint.sh` | Copies the mounted boards to a writable `/work/project`, then runs the command |
| `Dockerfile`, `pyproject.toml`, `uv.lock` | Own uv project and lock (`dbt-charts[snowflake]==0.9.1`), `uv sync --frozen --no-dev` |

Boards refer to dbt models with `{{ ref('mart_…') }}`. The compose service
mounts the dbt project files read-only at `/app/dbt`: `dbt_project.yml`,
`profiles.yml` and `target/` (the charts manifest). Build the manifest first
with `task dbt:parse TARGET=charts TARGET_PATH=target/charts` (`task dashboard`
does this). E2E points `CHARTS_MANIFEST_DIR` at its own directory.

## Things that differ from the docs

- **No `target_path` in 0.9.1.** The docs describe `target_path:` on the
  `dbt_profile` source, but 0.9.1 rejects it. It reads
  `<linked dbt project>/target/manifest.json`, so the manifest is mounted into
  `/app/dbt/target` and `DBT_PROJECT_DIR=/app/dbt`.
- **The v2 manifest works.** `ref()` resolves against the dbt v2 manifest
  (`dbt_schema_version` v12) without problems.
- **The timeout cap is on the Snowflake user.** `dct` sends its 120 s default
  with every query. `CHARTS_READER` and its warehouse have a 30 s
  `STATEMENT_TIMEOUT_IN_SECONDS` (`infra/snowflake/setup.sql`), and Snowflake
  applies the stricter value. The profile needs no `custom_settings`.
  `execution.max_query_duration_seconds` in `dbt_charts.yml` has no effect (it
  is read from the packaged defaults only), and the key is rejected on a
  `dbt_profile` source.
- **Column names are lower case.** Snowflake folds unquoted names to upper
  case, but `dct` returns `browser` and `submissions_count`, so the boards
  refer to columns exactly as in the SQL and need no quoting.
- **`dct doctor` does not exist in 0.9.1.** Use `dct validate --warehouse` and
  `dct query warehouse '<sql>'` (the source is named `warehouse`, not the
  board). Use fully qualified names there: `AICTX.MARTS.mart_browser_distribution`.
- **Column warnings are advisory.** `WARN-DBT-QUERY-COLUMNS-INDETERMINATE` and
  `WARN-COLUMN-CHECK-UNAVAILABLE` show up because Snowflake's `EXPLAIN` returns
  no result schema, so `dct` cannot check chart columns. `--strict` would fail
  on them, so lint does not use it. The render is the real check.
- **Each board query wakes the reader warehouse.** It auto-suspends after 60 s.
- **The container needs 1 GB.** `dct serve` grows to about 400 MB after serving
  the boards, and `task charts:validate` starts a second `dct` process in the
  same container. With the old 512 MB limit that second process was OOM-killed
  (exit 137, no output).

## Commands

| Task | What |
|---|---|
| `task dashboard` | Parse the charts manifest, start dbt Charts, open `/overview/` |
| `task charts:validate` | `dct validate --warehouse` in the running container |
| `task charts:render` | Render both boards to `renders/*.html` (gitignored) |
| `task charts:lint` | Lock check and static `dct validate` (lint runs this) |
