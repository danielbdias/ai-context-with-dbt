# Test strategy

Owner: `qa-expert` defines the pyramid and the gates. `test-automator`
implements and maintains the suites.

## Pyramid

| Layer | Covers | Run with | Needs |
|---|---|---|---|
| Unit | UA mapping, CSRF, validation, rate window, EL settings and config, dbt description coverage script, the sample-data generator, the Snowflake setup renderer, the MCP smoke helpers | `task test` | Nothing |
| Integration | Web writes against real Postgres, dlt merge against real Postgres and Snowflake (`@pytest.mark.integration`) | `task up && task test:integration` | Dev stack and a Snowflake account |
| dbt tests | Generic, custom and unit tests (staging dedup, tokens, accents, stopwords), source freshness (warn only), 100% description coverage including metrics, saved queries and semantic dimensions | `task dbt:build`, `task dbt:test`, `task dbt:freshness`, `task dbt:coverage` | Docker and Snowflake |
| Semantic validation | The generated `semantic_manifest.json` against MetricFlow's validator (see `docs/semantic-layer.md`) | by hand | Nothing |
| Board validation | `dct validate` (static in `task lint`, with `--warehouse` in `charts:validate`) | `task charts:validate` | Docker and Snowflake |
| Smoke | dbt-mcp over stdio, and a metric from the dbt platform equal to `count(*)` | `task mcp:smoke` | Docker, Snowflake and the dbt platform |
| E2E | The whole chain from an empty Postgres and an empty Snowflake database, in an isolated compose project | `task e2e` | Docker, Snowflake and admin credentials |

Async tests use anyio.

The integration tests reach Postgres through the published host port, so another
Postgres already bound to 5432 breaks them. Change `POSTGRES_PORT` in `.env`
(see the port 5432 entry in `docs/debugging.md`).

## Running

```bash
task lint                 # dbt coverage, ruff, format check, lock checks, static boards
task test                 # unit
task up && task test:integration
task dbt:test             # needs raw data: task seed && task el first
task charts:validate      # starts the charts container
task mcp:smoke            # needs DBT_HOST, DBT_TOKEN, DBT_PROD_ENV_ID in .env
task e2e                  # about 9 minutes, project aictx-e2e, needs SNOWFLAKE_ADMIN_*
E2E_KEEP=1 task e2e       # keep aictx-e2e and its database to debug, see docs/debugging.md
```

The e2e project uses its own Postgres volume, host ports (15432, 18000, 18090,
18081) and credentials (`scripts/e2e/e2e.env`), so it runs next to the dev stack
and never reads the dev `.env` for Postgres. The warehouse is real: each run
creates the Snowflake database `AICTX_E2E_<id>` and drops it afterwards. It uses
the dev account and service users, but never the dev database `AICTX`. A run
costs a few warehouse credits. See `scripts/e2e/README.md` for the stage layout
and helpers.

Without admin credentials the Snowflake stages skip and the Postgres stages
still run (`pytest -m e2e scripts/e2e`).

## Quality gates

A change is done when all of these hold:

1. `task lint` is green.
2. `task test` is green.
3. `task e2e` is green from a clean state (`task reset`, no leftover
   `aictx-e2e` volumes, `task e2e:clean` for databases).
4. New behaviour has a test, and a bug fix has a regression test.
5. A change to a metric or the semantic model passes the semantic validation and
   `task mcp:smoke` after the production job has run.

## E2E coverage map (plan section 6 asserts)

| # | Assert | Test |
|---|---|---|
| 1 | Stack healthy | `test_01_health.py::test_containers_healthy`, `test_postgres_databases` |
| 1 | Migrations applied | `test_01_health.py::test_migrations_applied`, `test_02_access.py::test_migrations_roundtrip` |
| 2 | 6 fixed-UA submissions, one row in all 3 tables | `test_03_submissions.py::test_good_submission_adds_one_row_per_table` (per sample) |
| 2 | 3 Chrome/macOS, 2 Firefox/Linux, 1 Mobile Safari/iOS | `test_03_submissions.py::test_sample_mix_is_three_chrome_two_firefox_one_safari` |
| 3 | Wrong password gives 401, no submission, failed audit row | `test_03_submissions.py::test_wrong_password_is_401_and_only_audited` |
| 4 | Missing or forged CSRF rejected | `test_03_submissions.py::test_missing_csrf_is_403`, `test_forged_csrf_is_403` |
| 4 | Message over 280 chars rejected | `test_03_submissions.py::test_message_over_280_chars_is_400` |
| 5 | EL twice, distinct ids = 6 both times | `test_04_el.py::test_el_is_idempotent` |
| 6 | Soft delete plus 7th row, raw has 7 ids | `test_04_el.py::test_soft_delete_and_new_row_propagate` |
| 6 | Staging `is_deleted` correct | `test_05_dbt.py::test_staging_flags_the_deleted_row` |
| 6 | A stale deleted duplicate in raw does not win the dedup | `test_05_dbt.py::test_staging_ignores_an_older_deleted_duplicate` |
| 7 | `dbt build` exits 0 | `test_05_dbt.py::test_dbt_build_succeeds` |
| 7 | `dbt docs generate` exits 0 | `test_05_dbt.py::test_dbt_docs_generate_succeeds` |
| 8 | Browser and OS counts match, deleted row excluded | `test_05_dbt.py::test_distributions_match_live_postgres_rows` |
| 8 | Word frequencies match, `café` and `cafe` merge | `test_05_dbt.py::test_word_frequencies_match_fixture`, `test_cafe_and_café_are_merged` |
| 8 | No stopwords, no tokens under 3 chars | `test_05_dbt.py::test_no_stopwords_and_no_short_tokens` |
| 9 | No `request_metadata` or `auth_attempts` in Snowflake | `test_04_el.py::test_auxiliary_tables_never_reach_snowflake` |
| 9 | Postgres side: `el_reader` sees `submissions` only | `test_02_access.py::test_el_reader_privileges` |
| 10 | Readers SELECT marts | `test_02_access.py::test_reader_allowed_and_denied`, `test_05_dbt.py::test_readers_select_the_built_marts` |
| 10 | Readers denied `RAW`, `STAGING`, account usage and every write | `test_02_access.py::test_reader_allowed_and_denied`, `test_reader_sees_only_marts_in_the_catalog` |
| 10 | Readers keep access after dbt rebuilds a table | `test_02_access.py::test_reader_survives_a_dbt_rebuild` |
| 10 | Reader timeout is 30 s and a session cannot raise it | `test_02_access.py::test_reader_timeout_is_configured_on_user_and_warehouse`, `test_reader_cannot_raise_its_own_timeout` |
| 10 | `dbt show --inline ... --target mcp` returns rows | `test_06_mcp.py::test_dbt_show_inline_target_mcp_returns_rows` |
| 10 | MCP exposes only the allowlist, queries are `MCP_READER` reads | `test_06_mcp.py::test_only_allowlisted_tools`, `test_mcp_session_read_only_as_mcp_reader`, `test_show_answers_top_browsers` |
| 11 | `dct render overview` succeeds with the right numbers | `test_07_dashboards.py::test_overview_board_renders`, `test_words_board_renders` |
| 11 | Charts endpoints return 200, boards validate on the warehouse | `test_07_dashboards.py::test_charts_http_endpoints`, `test_charts_validate_against_the_warehouse` |
| 11 | `CHARTS_READER` is limited to `MARTS` | `test_07_dashboards.py::test_charts_reader_is_marts_only` |

Beyond the plan: grants for `web_writer`, `EL_LOADER` and `DBT_RUNNER`, the
`updated_at` trigger, the CSP headers, the documented `show --select` denial, and
EL failing when the account is unreachable.

Not in e2e: the Semantic Layer. The dbt platform serves it from the dev database,
so a per-run database cannot be queried through it. `task mcp:smoke` covers it.

What the ClickHouse suite asserted and Snowflake cannot: `readonly=2`, per-query
row and memory caps, and `system.*` introspection. Those assertions were dropped,
not ported.

dbt 2.0.8 unit tests are real on Snowflake, including boolean expectations: the
staging test now asserts `is_deleted`, which ClickHouse could not express.
