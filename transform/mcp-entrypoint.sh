#!/bin/sh
# Start dbt-mcp. Compose passes DBT_HOST, DBT_TOKEN and DBT_PROD_ENV_ID as empty
# strings when .env leaves them blank, and dbt-mcp crashes on an empty
# DBT_PROD_ENV_ID (it parses it as an integer). Unset empties so the Semantic
# Layer tools are simply off until the platform is configured. DBT_HOST_PREFIX is
# optional and must be absent, not empty, when unused.
for name in DBT_HOST DBT_HOST_PREFIX DBT_TOKEN DBT_PROD_ENV_ID; do
    [ -n "$(printenv "$name")" ] || unset "$name"
done
exec dbt-mcp "$@"
