"""Fixtures for integration tests against a real Postgres (the dev stack)."""

import os
import uuid
from collections.abc import Callable, Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from web.auth import hash_ip
from web.main import create_app
from web.settings import Settings

PASSWORD = "itest-password"
CLIENT = ("203.0.113.7", 50000)


def owner_conninfo() -> str:
    """Connect as app_owner (the only role that can read messages back)."""
    return psycopg.conninfo.make_conninfo(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname="app",
        user="app_owner",
        password=os.environ["POSTGRES_APP_OWNER_PASSWORD"],
    )


@pytest.fixture
def run_id() -> str:
    """Unique token: used as IP salt and message prefix to isolate a test."""
    return uuid.uuid4().hex


@pytest.fixture
def make_settings(run_id: str) -> Callable[..., Settings]:
    """Return a Settings factory pointing at the dev Postgres."""

    def factory(**overrides: object) -> Settings:
        values = {
            "app_password": PASSWORD,
            "csrf_secret": "itest-csrf",
            "ip_salt": run_id,
            "postgres_host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "postgres_port": int(os.environ.get("POSTGRES_PORT", "5432")),
            "postgres_web_writer_password": os.environ["POSTGRES_WEB_WRITER_PASSWORD"],
            **overrides,
        }
        return Settings(**values)  # type: ignore[arg-type]

    return factory


@pytest.fixture
def owner() -> Iterator[psycopg.Connection]:
    """Autocommit owner connection for assertions and cleanup."""
    with psycopg.connect(owner_conninfo(), autocommit=True) as conn:
        yield conn


@pytest.fixture
def make_client(
    make_settings: Callable[..., Settings],
    run_id: str,
    owner: psycopg.Connection,
) -> Iterator[Callable[..., TestClient]]:
    """Return a TestClient factory; rows created by the run are deleted after."""
    clients: list[TestClient] = []

    def factory(**overrides: object) -> TestClient:
        client = TestClient(create_app(make_settings(**overrides)), client=CLIENT)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)
    owner.execute(
        "DELETE FROM app.auth_attempts WHERE ip_hash = ANY(%s)",
        ([hash_ip(CLIENT[0], run_id)],),
    )
    owner.execute("DELETE FROM app.submissions WHERE message LIKE %s", (f"{run_id}%",))
