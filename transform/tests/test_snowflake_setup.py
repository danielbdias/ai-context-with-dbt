"""Tests for the Snowflake setup runner: no account needed."""

import pytest

from scripts.snowflake_setup import (
    PASSWORD_VARIABLES,
    REQUIRED_ENV,
    SETUP_SQL,
    TEMPLATE_VARIABLE,
    drop_database,
    render,
    strip_comments,
    template_values,
    validate_database,
)

ENV = {name: f"value-of-{name.lower()}" for name in REQUIRED_ENV}


def test_render_fills_variables_and_drops_comment_lines() -> None:
    sql = "-- a comment; with a semicolon\nCREATE DATABASE <% database %>;\n"
    assert render(sql, {"database": "X1"}) == "CREATE DATABASE X1;"


def test_render_rejects_a_missing_variable() -> None:
    with pytest.raises(KeyError, match="database"):
        render("CREATE DATABASE <% database %>;", {})


@pytest.mark.parametrize("name", ["AICTX", "AICTX_E2E_AB12CD34"])
def test_database_names_that_are_accepted(name: str) -> None:
    assert validate_database(name) == name


@pytest.mark.parametrize("name", ["", "aictx", "A;DROP", "A B", "1AB", "A-B"])
def test_database_names_that_are_refused(name: str) -> None:
    with pytest.raises(ValueError):
        validate_database(name)


def test_template_values_need_every_credential() -> None:
    incomplete = {k: v for k, v in ENV.items() if k != "SNOWFLAKE_MCP_READER_PASSWORD"}
    with pytest.raises(KeyError, match="SNOWFLAKE_MCP_READER_PASSWORD"):
        template_values("AICTX", incomplete)


def test_setup_sql_uses_exactly_the_known_variables() -> None:
    used = set(TEMPLATE_VARIABLE.findall(strip_comments(SETUP_SQL.read_text())))
    assert used == {"database", *PASSWORD_VARIABLES}


def test_setup_sql_renders_completely_for_an_e2e_database() -> None:
    sql = render(SETUP_SQL.read_text(), template_values("AICTX_E2E_AB12CD34", ENV))
    assert "<%" not in sql
    assert "CREATE DATABASE IF NOT EXISTS AICTX_E2E_AB12CD34;" in sql
    assert "ON SCHEMA AICTX_E2E_AB12CD34.MARTS" in sql
    # No statement may still point at the dev database.
    assert "AICTX." not in sql.replace("AICTX_E2E_AB12CD34.", "")


def test_the_dev_database_cannot_be_dropped() -> None:
    with pytest.raises(ValueError, match="refusing"):
        drop_database("AICTX", ENV)
