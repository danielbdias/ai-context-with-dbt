"""Drop leftover per-run Snowflake databases (`task e2e:clean`).

A run that is killed before its teardown leaves an `AICTX_E2E_<id>` database
behind. It costs nothing while idle, but it is clutter. This drops every one.
The dev database `AICTX` never matches the pattern.
"""

from __future__ import annotations

import os
import sys

from scripts.snowflake_setup import admin_connection, drop_database

PATTERN = "AICTX_E2E_%"


def main() -> int:
    """Drop all databases that match the e2e naming pattern."""
    with admin_connection(os.environ) as connection:
        rows = connection.cursor().execute(f"SHOW DATABASES LIKE '{PATTERN}'")
        names = [row[1] for row in rows]
    for name in names:
        drop_database(name)
        print(f"dropped {name}")
    print(f"{len(names)} database(s) dropped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
