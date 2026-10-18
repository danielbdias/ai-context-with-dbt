# dbt Charts (`dct`)

Boards are YAML files in `charts/`. `dct serve` renders each one at
`/<file name>/`: `/overview/` and `/words/`. The warehouse is the dbt profile
`aictx`, target `charts`, which connects as `charts_reader` (SELECT on
`marts` only).

## Layout

| Path | What |
|---|---|
| `dbt_charts.yml` | The `warehouse` source (`type: dbt_profile`, profile `aictx`, target `charts`) and server settings |
| `charts/overview.yml` | KPI, two donuts, daily line, top browser×OS table |
| `charts/words.yml` | Top 30 words bar and the link to the Superset word cloud |
| `entrypoint.sh` | Copies the mounted boards to `/work/project` and fills in `SUPERSET_PORT` |
| `Dockerfile`, `pyproject.toml`, `uv.lock` | Own uv project and lock (`dbt-charts[clickhouse]==0.9.1`), `uv sync --frozen --no-dev` |

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
- **The timeout cap is on the profile.** `dct` sends its 120 s default with
  every query, and the reader profile caps `max_execution_time` at 30 s. The
  `charts` target in `transform/dbt/profiles.yml` sets
  `custom_settings.max_execution_time: 30`, and `dct` takes the stricter value.
  `execution.max_query_duration_seconds` in `dbt_charts.yml` has no effect
  (it is read from the packaged defaults only), and the key is rejected on a
  `dbt_profile` source.
- **Board Jinja has no `env_var`.** The link to Superset needs `SUPERSET_PORT`,
  so `entrypoint.sh` substitutes `__SUPERSET_PORT__` in the copied board.
- **`dct doctor` does not exist in 0.9.1.** Use `dct validate --warehouse` and
  `dct query warehouse '<sql>'`.
- **Column warnings are advisory.** `WARN-DBT-QUERY-COLUMNS-INDETERMINATE` shows
  up for `ref()` queries because ClickHouse gives `dct` no column schema.
  `--strict` would fail on them, so lint does not use it.

## Commands

| Task | What |
|---|---|
| `task dashboard` | Parse the charts manifest, start charts and Superset, open `/overview/` |
| `task charts:validate` | `dct validate --warehouse` in the running container |
| `task charts:render` | Render both boards to `renders/*.html` (gitignored) |
| `task charts:lint` | Lock check and static `dct validate` (lint runs this) |
