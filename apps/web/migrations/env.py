"""Alembic environment: raw SQL migrations run as `app_owner`.

The URL comes from `ALEMBIC_DATABASE_URL` if set, otherwise it is built from
`POSTGRES_HOST` (default 127.0.0.1), `POSTGRES_PORT` (default 5432) and
`POSTGRES_APP_OWNER_PASSWORD`.
"""

import os

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

VERSION_TABLE_SCHEMA = "app"


def database_url() -> str | URL:
    """Return the connection URL for the `app` database as `app_owner`."""
    if url := os.environ.get("ALEMBIC_DATABASE_URL"):
        return url
    return URL.create(
        "postgresql+psycopg",
        username="app_owner",
        password=os.environ["POSTGRES_APP_OWNER_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database="app",
    )


def run_migrations_online() -> None:
    """Run migrations in a transaction against the live database."""
    engine = create_engine(database_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            version_table_schema=VERSION_TABLE_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
