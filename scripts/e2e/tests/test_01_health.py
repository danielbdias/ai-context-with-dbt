"""Stage 1: the core stack is up and healthy with the expected settings."""

from scripts.e2e.helpers import ch_query, container_health, pg_query


def test_containers_healthy() -> None:
    health = container_health()
    assert health["postgres"] == "healthy"
    assert health["clickhouse"] == "healthy"
    assert health["web"] == "healthy"


def test_postgres_databases() -> None:
    assert pg_query("select 1", db="app") == [(1,)]
    rows = pg_query("select datname from pg_database")
    assert {"app", "superset"} <= {name for (name,) in rows}


def test_clickhouse_alive_and_memory_ratio() -> None:
    assert ch_query("SELECT 1") == [(1,)]
    rows = ch_query(
        "SELECT value FROM system.server_settings "
        "WHERE name = 'max_server_memory_usage_to_ram_ratio'"
    )
    assert float(rows[0][0]) == 0.75


def test_migrations_applied() -> None:
    """Alembic is at a revision and the three app tables exist."""
    assert pg_query("SELECT count(*) FROM app.alembic_version")[0][0] == 1
    tables = {
        name
        for (name,) in pg_query(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = 'app'"
        )
    }
    assert {"submissions", "request_metadata", "auth_attempts"} <= tables
