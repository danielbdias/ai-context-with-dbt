#!/bin/bash
# Creates the login roles and the `app` schema. Runs once, after
# 01-databases.sql. Passwords come from the container environment.
# Table-level grants live in the Alembic migration, not here.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres \
  -v owner_pw="$POSTGRES_APP_OWNER_PASSWORD" \
  -v writer_pw="$POSTGRES_WEB_WRITER_PASSWORD" \
  -v reader_pw="$POSTGRES_EL_READER_PASSWORD" <<'SQL'
CREATE ROLE app_owner     LOGIN PASSWORD :'owner_pw';
CREATE ROLE web_writer    LOGIN PASSWORD :'writer_pw';
CREATE ROLE el_reader     LOGIN PASSWORD :'reader_pw';

-- Nobody connects by default (PUBLIC has CONNECT and TEMP on new databases).
REVOKE ALL ON DATABASE postgres, app FROM PUBLIC;
GRANT CONNECT ON DATABASE app TO app_owner, web_writer, el_reader;

\connect app
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA app AUTHORIZATION app_owner;

SQL
