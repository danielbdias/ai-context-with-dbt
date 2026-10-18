# Superset (word cloud only)

Superset 6.1.0 serves one thing: the native **Word Cloud** chart over
`marts.mart_word_frequencies`. Every other chart is a dbt Charts board
(`dashboard/charts`). The `superset` service listens on
`http://127.0.0.1:${SUPERSET_PORT}`, and the word cloud is at
`/superset/dashboard/word-cloud/`.

## What starts

| Service | Image | Role |
|---|---|---|
| `superset-init` | `aictx-superset:local` | One-shot: `db upgrade`, admin, `superset init`, import the bundle |
| `superset` | same | Gunicorn server, healthcheck on `/health` |

The metadata DB is database `superset` on the shared Postgres, owned by
`superset_meta` (`infra/postgres/init/02-roles.sh`). The ClickHouse connection
is `superset_reader` (grants: `SELECT` on `marts.mart_word_frequencies` only).

## Driver install (lock-based, no pip)

The image `apache/superset:6.1.0` ships neither `clickhouse_connect` nor a
Postgres driver (checked with `docker run --rm apache/superset:6.1.0 python -c
"import clickhouse_connect"`, which fails). `Dockerfile` installs them from
`uv.lock` into the image's own venv:

```
UV_PROJECT_ENVIRONMENT=/app/.venv uv sync --frozen --inexact --no-install-project
```

- `clickhouse-connect==0.15.1`: the newest 0.x. Superset 6.1.0 declares its
  ClickHouse extra as `clickhouse-connect>=0.13.0,<1.0`, so 1.x is outside its
  range.
- `psycopg2-binary==2.9.9`: the pin of Superset's own `postgres` extra.
- `constraint-dependencies` hold every package the lock shares with the image
  (`certifi`, `cffi`, `pycparser`, `pytz`, `urllib3`, `zstandard`) at the
  image's version. `--inexact` then adds two packages and changes none.

Re-lock with the image's own uv and Python 3.10 (the host has neither):

```
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e UV_CACHE_DIR=/tmp/uvcache \
  -v "$PWD/dashboard/superset:/work" -w /work --entrypoint uv \
  apache/superset:6.1.0 lock
```

`task lint` runs `uv lock --check` the same way.

## Secrets

- `superset_config.py` reads `SUPERSET_SECRET_KEY` and the Postgres password
  from the environment. The image refuses to start with its default key.
- The admin user is `admin`, password `SUPERSET_ADMIN_PASSWORD` (from `.env`).
  `init.sh` creates it only when missing.
- `bundle/` is committed without secrets. `databases/ClickHouse_marts.yaml`
  holds the placeholder `__CLICKHOUSE_SUPERSET_READER_PASSWORD__`.
  `render_bundle.py` fills it from `CLICKHOUSE_SUPERSET_READER_PASSWORD`
  (URL-encoded) into a temporary ZIP at import time. Unit tests and the e2e
  stage grep the bundle for secrets.

## Access

The dashboard needs a login (`admin`, `.env`). The `Public` role has no
permissions, so anonymous visitors are redirected to the login page. The
words board links to the word cloud with the login path.

## Import behaviour

`init.sh` runs `superset import-dashboards -p <zip> -u admin`. Objects match by
UUID, so re-running `superset-init` updates them in place. Checked: a second
run leaves one dashboard, one chart, one dataset and one database.

## Author or update the bundle (one-time, documented)

The bundle was authored through the Superset REST API and then exported, so
Superset generated the YAML. To change the word cloud:

1. Start the stack with the current bundle: `task dashboard`.
2. Log in to the API as `admin` (`POST /api/v1/security/login`, then
   `GET /api/v1/security/csrf_token/` and send `X-CSRFToken` on writes).
3. Make the change in the UI at `http://127.0.0.1:${SUPERSET_PORT}`, or through
   the API. Keep chart `uuid`s and the dashboard `slug` (`word-cloud`).
4. Export inside the container, then copy the export out:
   `docker compose --profile core --profile dashboard exec superset superset export-dashboards -f /tmp/word-cloud-export.zip`
   and `docker compose cp superset:/tmp/word-cloud-export.zip .`.
5. Extract it into `bundle/`, keeping the export layout (`metadata.yaml`,
   `databases/`, `datasets/`, `charts/`, `dashboards/`).
6. In `databases/ClickHouse_marts.yaml`, replace the export's `XXXXXXXXXX` with
   `__CLICKHOUSE_SUPERSET_READER_PASSWORD__`.
7. Check with `uv run pytest dashboard/superset/tests`, then grep the bundle for
   `password:` and the secret values.

Lessons from authoring:

- A chart must carry the dashboard's position `uuid` in its layout `meta`.
  Without it, the export adds a second, auto-generated row with the same chart.
- `GET /api/v1/chart/<id>/data/` needs a saved `query_context`, which the UI
  writes. For the API check, `POST /api/v1/chart/data` with an explicit query
  context works (this is what the e2e stage uses).
- The word cloud chart's params are `series` (the text column), `metric` (an
  adhoc `SUM(frequency)`), `row_limit`, `size_from`, `size_to`, `rotation` and
  `color_scheme`. These match the example chart shipped in the image at
  `superset/examples/featured_charts/charts/Word_Cloud.yaml`.
