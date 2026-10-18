"""Config builders: no network."""

import pytest
from el.settings import Settings, clickhouse_credentials, postgres_url


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_EL_READER_PASSWORD", "p@ss/word")
    monkeypatch.setenv("CLICKHOUSE_HOST", "clickhouse")
    monkeypatch.setenv("CLICKHOUSE_EL_LOADER_PASSWORD", "ch-secret")
    return Settings()  # type: ignore[call-arg]


def test_postgres_url_uses_reader_role_and_psycopg3(settings: Settings) -> None:
    url = postgres_url(settings)
    assert url.startswith("postgresql+psycopg://el_reader:")
    assert url.endswith("@postgres:5432/app")
    assert "p%40ss%2Fword" in url


def test_clickhouse_credentials(settings: Settings) -> None:
    assert clickhouse_credentials(settings) == {
        "host": "clickhouse",
        "port": 9000,
        "http_port": 8123,
        "username": "el_loader",
        "password": "ch-secret",
        "database": "raw",
        "secure": 0,
    }


def test_defaults(settings: Settings) -> None:
    assert settings.el_incremental_lag_seconds == 5
    assert settings.el_max_attempts == 3


def test_missing_password_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_EL_READER_PASSWORD", raising=False)
    monkeypatch.delenv("CLICKHOUSE_EL_LOADER_PASSWORD", raising=False)
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]
