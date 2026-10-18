# Build context is the repository root (the uv workspace lock lives there):
#   docker build -f transform/Dockerfile --target dbt .
# Targets:
#   dbt      one-shot dbt v2 runner (build, test, freshness, docs)
#   dbt-mcp  the same plus the dbt-mcp stdio server (finished in M7)
FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

FROM python:3.13.16-slim-trixie AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so source edits do not invalidate this layer.
COPY pyproject.toml uv.lock ./
COPY apps/web/pyproject.toml apps/web/pyproject.toml
COPY apps/el/pyproject.toml apps/el/pyproject.toml
COPY transform/pyproject.toml transform/pyproject.toml
RUN uv sync --frozen --package transform --no-dev --no-install-workspace

COPY transform/src transform/src
RUN uv sync --frozen --package transform --no-dev

# dbt v2 talks to ClickHouse through an ADBC driver that it downloads on first
# use. Download it now, at build time, so containers run offline and start
# fast. `install-drivers` fetches every warehouse driver (about 500 MB), so keep
# only ClickHouse (the warehouse) and DuckDB (`dbt docs generate` and
# `docs serve` read project metadata through it).
ENV XDG_CACHE_HOME=/opt/dbt-cache
RUN /app/.venv/bin/dbt system install-drivers \
    && find "$XDG_CACHE_HOME" -name 'libadbc_driver_*' \
        ! -name 'libadbc_driver_clickhouse*' ! -name 'libadbc_driver_duckdb*' \
        -delete \
    && find "$XDG_CACHE_HOME" -type f

FROM python:3.13.16-slim-trixie AS base
# git: `dbt debug` checks for it and `dbt deps` needs it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/opt/dbt-cache \
    DBT_PROJECT_DIR=/app/transform/dbt \
    DBT_PROFILES_DIR=/app/transform/dbt \
    DBT_DISABLE_VERSION_CHECK=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false
WORKDIR /app/transform/dbt
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /opt/dbt-cache /opt/dbt-cache
COPY --chown=app:app transform/dbt /app/transform/dbt
USER app

FROM base AS dbt
ENTRYPOINT ["dbt"]
CMD ["build"]

FROM base AS dbt-mcp
# TODO(M7): configure the allowlist, target and read-only environment.
ENTRYPOINT ["dbt-mcp"]
