#!/bin/bash
# Creates databases, the `reader` settings profile, users and grants.
# Runs once on first start. Passwords come from the container environment and
# are stored as SHA-256 hashes (the plaintext never appears in a query).
set -euo pipefail

sha256() { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }

clickhouse-client --multiquery --host 127.0.0.1 \
  --user "${CLICKHOUSE_USER:-default}" --password "${CLICKHOUSE_PASSWORD:-}" <<SQL
CREATE DATABASE raw;
CREATE DATABASE raw_staging;
CREATE DATABASE staging;
CREATE DATABASE marts;

-- Readers: readonly=2 allows per-query SETTINGS, so every limit is pinned by a
-- range. MIN 1 matters: 0 means "unlimited" and would pass a bare MAX.
CREATE SETTINGS PROFILE reader SETTINGS
  readonly = 2,
  max_execution_time = 30 MIN 1 MAX 30,
  max_result_rows = 10000 MIN 1 MAX 10000,
  max_memory_usage = 1000000000 MIN 1 MAX 1000000000,
  result_overflow_mode = 'throw' CONST;

CREATE USER el_loader IDENTIFIED WITH sha256_hash BY '$(sha256 "$CLICKHOUSE_EL_LOADER_PASSWORD")';
CREATE USER dbt_runner IDENTIFIED WITH sha256_hash BY '$(sha256 "$CLICKHOUSE_DBT_RUNNER_PASSWORD")';
CREATE USER mcp_reader IDENTIFIED WITH sha256_hash BY '$(sha256 "$CLICKHOUSE_MCP_READER_PASSWORD")' SETTINGS PROFILE 'reader';
CREATE USER charts_reader IDENTIFIED WITH sha256_hash BY '$(sha256 "$CLICKHOUSE_CHARTS_READER_PASSWORD")' SETTINGS PROFILE 'reader';
CREATE USER superset_reader IDENTIFIED WITH sha256_hash BY '$(sha256 "$CLICKHOUSE_SUPERSET_READER_PASSWORD")' SETTINGS PROFILE 'reader';

-- el_loader (dlt): owns raw and raw_staging. ALTER covers ADD COLUMN for
-- schema evolution as well as ALTER DELETE/UPDATE for merges.
GRANT CREATE TABLE, DROP TABLE, INSERT, SELECT, ALTER, TRUNCATE ON raw.* TO el_loader;
GRANT CREATE TABLE, DROP TABLE, INSERT, SELECT, ALTER, TRUNCATE ON raw_staging.* TO el_loader;
GRANT SELECT ON system.tables TO el_loader;
GRANT SELECT ON system.columns TO el_loader;
GRANT SELECT ON system.databases TO el_loader;

-- dbt_runner: reads raw, owns staging and marts.
GRANT SELECT ON raw.* TO dbt_runner;
GRANT CREATE TABLE, CREATE VIEW, DROP TABLE, DROP VIEW, INSERT, SELECT, ALTER, TRUNCATE ON staging.* TO dbt_runner;
GRANT CREATE TABLE, CREATE VIEW, DROP TABLE, DROP VIEW, INSERT, SELECT, ALTER, TRUNCATE ON marts.* TO dbt_runner;
GRANT SELECT ON system.tables TO dbt_runner;
GRANT SELECT ON system.columns TO dbt_runner;
GRANT SELECT ON system.databases TO dbt_runner;
GRANT SELECT ON system.settings TO dbt_runner;
GRANT SELECT ON system.functions TO dbt_runner;

-- Readers: marts only, no system tables. The table-level grant for
-- superset_reader is accepted before the table exists, and survives dbt
-- dropping and recreating it.
GRANT SELECT ON marts.* TO mcp_reader;
GRANT SELECT ON marts.* TO charts_reader;
GRANT SELECT ON marts.mart_word_frequencies TO superset_reader;
SQL
