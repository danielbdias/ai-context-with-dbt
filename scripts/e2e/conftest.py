"""Pytest wiring: mark everything under scripts/e2e as `e2e`, set up the stores."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest

from scripts.e2e.helpers import E2E_DATABASE, pg_query
from scripts.snowflake_setup import (
    REQUIRED_ENV,
    drop_database,
    run_setup,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply the `e2e` marker to every collected e2e test."""
    for item in items:
        if "scripts/e2e" in item.nodeid:
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session", autouse=True)
def postgres_reachable() -> None:
    """Wait until Postgres answers from the host."""
    deadline = time.monotonic() + 60
    while True:
        try:
            pg_query("select 1")
            return
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)


@pytest.fixture(scope="session")
def e2e_database() -> Iterator[str]:
    """A per-run Snowflake database with the demo schemas, roles and grants.

    Created by running infra/snowflake/setup.sql for `E2E_DATABASE` and dropped
    afterwards, also when tests fail. `E2E_KEEP=1` keeps it for debugging, and
    `task e2e:clean` removes leftovers. Skips when the credentials are missing,
    so the Postgres-only stages still run.
    """
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        pytest.skip(f"the Snowflake stages need {', '.join(missing)}")
    run_setup(E2E_DATABASE)
    try:
        yield E2E_DATABASE
    finally:
        if os.environ.get("E2E_KEEP"):
            print(f"\nE2E_KEEP set: database {E2E_DATABASE} left in place")
        else:
            drop_database(E2E_DATABASE)
