"""Pytest wiring: mark everything under scripts/e2e as `e2e`."""

from __future__ import annotations

import time

import pytest

from scripts.e2e.helpers import ch_query, pg_query


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply the `e2e` marker to every collected e2e test."""
    for item in items:
        if "scripts/e2e" in item.nodeid:
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session", autouse=True)
def stores_reachable() -> None:
    """Wait until both databases answer from the host.

    The ClickHouse image runs a temporary server during init, so the container
    healthcheck can pass a moment before the real server accepts host traffic.
    """
    deadline = time.monotonic() + 60
    for probe in (lambda: pg_query("select 1"), lambda: ch_query("SELECT 1")):
        while True:
            try:
                probe()
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
