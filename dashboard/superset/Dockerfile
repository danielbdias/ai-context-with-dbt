# Build context is dashboard/superset (its own uv lock, not a workspace member):
#   docker build -f dashboard/superset/Dockerfile dashboard/superset
# Superset 6.1.0 plus the drivers this demo needs. The image ships neither the
# ClickHouse driver nor a Postgres driver, so both come from uv.lock into the
# image's own venv. --inexact keeps every package the image already has.
FROM apache/superset:6.1.0

USER root
COPY pyproject.toml uv.lock /tmp/driver/
RUN cd /tmp/driver \
    && UV_PROJECT_ENVIRONMENT=/app/.venv uv sync --frozen --inexact --no-install-project --no-cache \
    && rm -rf /tmp/driver

# The image loads superset_config from PYTHONPATH (/app/pythonpath).
COPY superset_config.py /app/pythonpath/superset_config.py
COPY init.sh render_bundle.py /app/aictx/
COPY bundle /app/aictx/bundle
RUN chmod 0755 /app/aictx/init.sh

USER superset
