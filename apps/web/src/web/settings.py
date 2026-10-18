"""Application settings read from environment variables."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(extra="ignore")

    app_password: SecretStr
    csrf_secret: SecretStr
    ip_salt: SecretStr
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "app"
    postgres_web_writer_password: SecretStr
    rate_limit_max: int = 5
    rate_limit_window_seconds: int = 900
    message_max_length: int = 280
    user_agent_max_length: int = 1024
    accept_language_max_length: int = 128
