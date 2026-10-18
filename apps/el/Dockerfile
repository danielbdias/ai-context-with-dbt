# Build context is the repository root (the uv workspace lock lives there):
#   docker build -f apps/el/Dockerfile .
# One-shot image: `python -m el.pipeline` copies app.submissions to ClickHouse.
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
RUN uv sync --frozen --package el --no-dev --no-install-workspace

COPY apps/el apps/el
RUN uv sync --frozen --package el --no-dev

FROM python:3.13.16-slim-trixie AS runtime
# The pipelines dir is a temp dir per run: state is restored from ClickHouse.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    DLT_DATA_DIR=/tmp/dlt \
    RUNTIME__DLTHUB_TELEMETRY=false
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=builder /app /app
USER app
CMD ["python", "-m", "el.pipeline"]
