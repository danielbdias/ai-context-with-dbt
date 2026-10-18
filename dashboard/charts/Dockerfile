# Build context is dashboard/charts (its own uv project and lock, not a member
# of the root workspace):
#   docker build -f dashboard/charts/Dockerfile dashboard/charts
# The image holds the dbt Charts CLI (`dct`) only. Compose mounts the boards,
# dbt_charts.yml and the dbt project files read-only.
FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

FROM python:3.13.16-slim-trixie
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

# Dependencies first, so board edits do not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /work && chown app /work
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    DBT_LOG_PATH=/tmp/dbt-logs \
    DBT_PROJECT_DIR=/app/dbt \
    DBT_PROFILES_DIR=/app/dbt \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    DBT_DISABLE_VERSION_CHECK=1 \
    DO_NOT_TRACK=1

USER app
EXPOSE 8090
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["dct", "serve", "--host", "0.0.0.0", "--port", "8090"]
