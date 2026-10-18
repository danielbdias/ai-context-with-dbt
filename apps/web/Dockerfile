# Build context is the repository root (the uv workspace lock lives there):
#   docker build -f apps/web/Dockerfile .
# The same image runs the app (uvicorn) and the Alembic migrations.
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
RUN uv sync --frozen --package web --no-dev --no-install-workspace

COPY apps/web apps/web
RUN uv sync --frozen --package web --no-dev

FROM python:3.13.16-slim-trixie AS runtime
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=builder /app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "web.main:create_app", "--factory", "--host", "0.0.0.0", \
     "--port", "8000", "--no-access-log"]
