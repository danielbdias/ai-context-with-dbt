"""Typed EL configuration read from environment variables."""

from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PG_ROLE = "el_reader"
SNOWFLAKE_USER = "EL_LOADER"
SNOWFLAKE_ROLE = "AICTX_EL_LOADER"
SNOWFLAKE_WAREHOUSE = "AICTX_LOAD_WH"
SNOWFLAKE_DATASET = "raw"


class Settings(BaseSettings):
    """Runtime configuration. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(extra="ignore")

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "app"
    postgres_el_reader_password: SecretStr
    snowflake_account: str
    snowflake_database: str = "AICTX"
    snowflake_el_loader_password: SecretStr
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


def snowflake_credentials(settings: Settings) -> dict[str, Any]:
    """Credentials dict for dlt's Snowflake destination (`host` is the account)."""
    return {
        "host": settings.snowflake_account,
        "database": settings.snowflake_database,
        "username": SNOWFLAKE_USER,
        "password": settings.snowflake_el_loader_password.get_secret_value(),
        "warehouse": SNOWFLAKE_WAREHOUSE,
        "role": SNOWFLAKE_ROLE,
    }
