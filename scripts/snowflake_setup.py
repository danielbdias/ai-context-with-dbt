"""Run infra/snowflake/setup.sql as an admin (`task snowflake:setup`).

The script holds template variables (`<% name %>`): the database name and the
four service passwords. This module fills them in and executes the result, so
`task snowflake:setup` and the e2e suite share one implementation.

    task snowflake:setup                       # the dev database, AICTX
    uv run python -m scripts.snowflake_setup AICTX_E2E_AB12CD34

Reads SNOWFLAKE_ACCOUNT, SNOWFLAKE_ADMIN_USER, SNOWFLAKE_ADMIN_PASSWORD and the
four SNOWFLAKE_*_PASSWORD variables. Every statement is idempotent.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

import snowflake.connector
from snowflake.connector import SnowflakeConnection

SETUP_SQL = Path(__file__).resolve().parent.parent / "infra" / "snowflake" / "setup.sql"
TEMPLATE_VARIABLE = re.compile(r"<%\s*(\w+)\s*%>")
DATABASE_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
DEFAULT_DATABASE = "AICTX"
PASSWORD_VARIABLES = {
    "el_loader_password": "SNOWFLAKE_EL_LOADER_PASSWORD",
    "dbt_runner_password": "SNOWFLAKE_DBT_RUNNER_PASSWORD",
    "mcp_reader_password": "SNOWFLAKE_MCP_READER_PASSWORD",
    "charts_reader_password": "SNOWFLAKE_CHARTS_READER_PASSWORD",
}
REQUIRED_ENV = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_ADMIN_USER",
    "SNOWFLAKE_ADMIN_PASSWORD",
    *PASSWORD_VARIABLES.values(),
)


def validate_database(name: str) -> str:
    """Return `name` if it is a plain upper-case identifier, else raise.

    The name is interpolated into SQL, so anything but letters, digits and
    underscores is refused.
    """
    if not DATABASE_NAME.fullmatch(name):
        raise ValueError(f"not a plain upper-case database name: {name!r}")
    return name


def render(sql: str, values: Mapping[str, str]) -> str:
    """Fill `<% name %>` variables and drop full-line comments.

    Raises:
        KeyError: A variable in the SQL has no value.
    """
    body = strip_comments(sql)
    missing = sorted(set(TEMPLATE_VARIABLE.findall(body)) - set(values))
    if missing:
        raise KeyError(f"no value for template variable(s): {', '.join(missing)}")
    return TEMPLATE_VARIABLE.sub(lambda match: values[match.group(1)], body)


def strip_comments(sql: str) -> str:
    """Drop full-line `--` comments, which may contain semicolons."""
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def template_values(database: str, env: Mapping[str, str]) -> dict[str, str]:
    """Template values: the database plus the service passwords from `env`."""
    missing = [name for name in REQUIRED_ENV if not env.get(name)]
    if missing:
        raise KeyError(f"set {', '.join(missing)}")
    values = {name: env[var] for name, var in PASSWORD_VARIABLES.items()}
    return {"database": validate_database(database), **values}


def admin_connection(env: Mapping[str, str]) -> SnowflakeConnection:
    """Connect as the admin user with the ACCOUNTADMIN role."""
    return snowflake.connector.connect(
        account=env["SNOWFLAKE_ACCOUNT"],
        user=env["SNOWFLAKE_ADMIN_USER"],
        password=env["SNOWFLAKE_ADMIN_PASSWORD"],
        role="ACCOUNTADMIN",
    )


def run_setup(database: str, env: Mapping[str, str] | None = None) -> None:
    """Create `database` with the demo schemas, roles, users and grants."""
    env = env if env is not None else os.environ
    sql = render(SETUP_SQL.read_text(), template_values(database, env))
    with admin_connection(env) as connection:
        connection.execute_string(sql)


def drop_database(database: str, env: Mapping[str, str] | None = None) -> None:
    """Drop `database`. Refuses the dev database, so a mistake cannot delete it."""
    if validate_database(database) == DEFAULT_DATABASE:
        raise ValueError(f"refusing to drop the dev database {DEFAULT_DATABASE}")
    env = env if env is not None else os.environ
    with admin_connection(env) as connection:
        connection.cursor().execute(f"DROP DATABASE IF EXISTS {database}")


def main(argv: list[str]) -> int:
    """Set up the database named in argv[0] (default: the dev database)."""
    database = (
        argv[0] if argv else os.environ.get("SNOWFLAKE_DATABASE", DEFAULT_DATABASE)
    )
    try:
        run_setup(database)
    except (KeyError, ValueError) as error:
        print(f"error: {error.args[0]}", file=sys.stderr)
        return 1
    print(f"set up database {database}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
