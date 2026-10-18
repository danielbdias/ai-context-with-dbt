"""Typed EL configuration read from environment variables."""

from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PG_ROLE = "el_reader"
CH_ROLE = "el_loader"


class Settings(BaseSettings):
    """Runtime configuration. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(extra="ignore")

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "app"
    postgres_el_reader_password: SecretStr
    clickhouse_host: str = "127.0.0.1"
    clickhouse_native_port: int = 9000
    clickhouse_http_port: int = 8123
    clickhouse_database: str = "raw"
    clickhouse_secure: bool = False
    clickhouse_el_loader_password: SecretStr
    el_incremental_lag_seconds: int = 5
    el_max_attempts: int = 3
    el_retry_delay_seconds: float = 5.0


def postgres_url(settings: Settings) -> str:
    """SQLAlchemy URL for the read-only source (psycopg 3 dialect)."""
    return URL.create(
        "postgresql+psycopg",
        username=PG_ROLE,
        password=settings.postgres_el_reader_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    ).render_as_string(hide_password=False)


def clickhouse_credentials(settings: Settings) -> dict[str, Any]:
    """Credentials dict for dlt's ClickHouse destination."""
    return {
        "host": settings.clickhouse_host,
        "port": settings.clickhouse_native_port,
        "http_port": settings.clickhouse_http_port,
        "username": CH_ROLE,
        "password": settings.clickhouse_el_loader_password.get_secret_value(),
        "database": settings.clickhouse_database,
        "secure": int(settings.clickhouse_secure),
    }
