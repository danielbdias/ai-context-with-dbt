# Build context is the repository root (the uv workspace lock lives there):
#   docker build -f transform/Dockerfile --target dbt .
# Targets:
#   dbt      one-shot dbt v2 runner (build, test, freshness, docs)
#   dbt-mcp  the same image running the read-only dbt-mcp stdio server
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
# dbt-mcp over stdio, read-only: target `mcp` (mcp_reader) and an allowlist of
# six tools. Allowlist mode (DBT_MCP_ENABLE_TOOLS) registers nothing else, so
# build/run/test/clone/docs and every dbt platform tool are absent.
# Artifacts go to target_mcp/. `get_lineage_dev` reads target/manifest.json
# (hard-coded in dbt-mcp), so compose mounts the same volume at both paths.
# stdout carries JSON-RPC only: dbt-mcp logs to stderr. DBT_QUIET keeps dbt's
# banner out of tool results (errors still come through).
ENV DBT_PATH=/app/.venv/bin/dbt \
    DBT_TARGET=mcp \
    DBT_TARGET_PATH=target_mcp \
    DBT_LOG_PATH=/tmp/dbt-logs \
    DBT_QUIET=true \
    DBT_CLI_TIMEOUT=60 \
    DBT_MCP_ENABLE_TOOLS=show,list,compile,parse,get_node_details_dev,get_lineage_dev \
    DBT_MCP_LOG_LEVEL=INFO \
    DBT_ENGINE_NO_WARN_SEMANTIC_MANIFEST_VALIDATION=1 \
    DISABLE_MCP_APPS=true \
    DO_NOT_TRACK=1 \
    MCP_TRANSPORT=stdio
ENTRYPOINT ["dbt-mcp"]
