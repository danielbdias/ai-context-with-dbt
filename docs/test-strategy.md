# Test strategy

Owner: `qa-expert` defines the pyramid and the gates. `test-automator`
implements and maintains the suites.

## Pyramid

| Layer | Covers | Run with | Needs Docker |
|---|---|---|---|
| Unit | UA mapping, CSRF, validation, rate window, EL settings and config, bundle rendering, dbt description coverage script | `task test` | No |
| Integration | Web writes against real Postgres, dlt merge against real Postgres and ClickHouse (`@pytest.mark.integration`) | `task up && task test:integration` | Yes (dev stack) |
| dbt tests | Generic, custom and unit tests (staging dedup, tokens, accents, stopwords), source freshness (warn only), 100% description coverage | `task dbt:build`, `task dbt:test`, `task dbt:freshness`, `task dbt:coverage` | Yes |
| Board validation | `dct validate` (static in `task lint`, with `--warehouse` in `charts:validate`) | `task charts:validate` | Yes |
| E2E | The whole chain from empty volumes, in an isolated compose project | `task e2e` | Yes |

Async tests use anyio.

## Running

```bash
task lint                 # dbt coverage, ruff, format check, 3 lock checks, static boards
task test                 # unit
task up && task test:integration
task dbt:test             # needs raw data: task seed && task el first
task charts:validate      # starts the charts container
task e2e                  # about 1 to 3 minutes warm, project aictx-e2e
E2E_KEEP=1 task e2e       # leave aictx-e2e running to debug, see docs/debugging.md
```

The e2e project uses its own volumes, host ports (15432, 18123, 19000, 18000,
18090, 18088, 18081) and credentials (`scripts/e2e/e2e.env`), so it runs next
to the dev stack and never reads the dev `.env`. See `scripts/e2e/README.md`
for the stage layout and helpers.

## Quality gates

A change is done when all of these hold:

1. `task lint` is green.
2. `task test` is green.
3. `task e2e` is green twice in a row from a clean state (`task reset`, no
   leftover `aictx-e2e` volumes).
4. New behaviour has a test, and a bug fix has a regression test.

## E2E coverage map (plan section 6 asserts)

| # | Assert | Test |
|---|---|---|
| 1 | Stack healthy | `test_01_health.py::test_containers_healthy`, `test_postgres_databases`, `test_clickhouse_alive_and_memory_ratio` |
| 1 | Migrations applied | `test_01_health.py::test_migrations_applied`, `test_02_access.py::test_migrations_roundtrip` |
| 2 | 6 fixed-UA submissions, one row in all 3 tables | `test_03_submissions.py::test_good_submission_adds_one_row_per_table` (per sample) |
| 2 | 3 Chrome/macOS, 2 Firefox/Linux, 1 Mobile Safari/iOS | `test_03_submissions.py::test_sample_mix_is_three_chrome_two_firefox_one_safari` |
| 3 | Wrong password gives 401, no submission, failed audit row | `test_03_submissions.py::test_wrong_password_is_401_and_only_audited` |
| 4 | Missing or forged CSRF rejected | `test_03_submissions.py::test_missing_csrf_is_403`, `test_forged_csrf_is_403` |
| 4 | Message over 280 chars rejected | `test_03_submissions.py::test_message_over_280_chars_is_400` |
| 5 | EL twice, `uniqExact(id)` = 6 both times | `test_04_el.py::test_el_is_idempotent` |
| 6 | Soft delete plus 7th row, raw has 7 ids | `test_04_el.py::test_soft_delete_and_new_row_propagate` |
| 6 | Staging `is_deleted` correct | `test_05_dbt.py::test_staging_flags_the_deleted_row` |
| 6 | A stale deleted duplicate in raw does not win the dedup | `test_05_dbt.py::test_staging_ignores_an_older_deleted_duplicate` |
| 7 | `dbt build` exits 0 | `test_05_dbt.py::test_dbt_build_succeeds` |
| 7 | `dbt docs generate` exits 0 | `test_05_dbt.py::test_dbt_docs_generate_succeeds` |
| 8 | Browser and OS counts match, deleted row excluded | `test_05_dbt.py::test_distributions_match_live_postgres_rows` |
| 8 | Word frequencies match, `café` and `cafe` merge | `test_05_dbt.py::test_word_frequencies_match_fixture`, `test_cafe_and_café_are_merged` |
| 8 | No stopwords, no tokens under 3 chars | `test_05_dbt.py::test_no_stopwords_and_no_short_tokens` |
| 9 | No `request_metadata` or `auth_attempts` in ClickHouse | `test_04_el.py::test_auxiliary_tables_never_reach_clickhouse` |
| 9 | Postgres side: `el_reader` sees `submissions` only | `test_02_access.py::test_el_reader_privileges` |
| 10 | Readers SELECT marts | `test_02_access.py::test_reader_allowed_and_denied`, `test_05_dbt.py::test_readers_select_the_built_marts` |
| 10 | Readers denied raw, staging, `system.query_log`, INSERT | `test_02_access.py::test_reader_allowed_and_denied` |
| 10 | Readers denied `SETTINGS max_result_rows=0` and other overrides | `test_02_access.py::test_reader_allowed_and_denied`, `test_reader_limits_are_enforced`, `test_reader_row_cap` |
| 10 | Superset reader limited to the word table | `test_02_access.py::test_superset_reader_is_table_scoped`, `test_07_dashboards.py::test_superset_reader_is_word_table_only` |
| 10 | `dbt show --inline ... --target mcp` returns rows | `test_06_mcp.py::test_dbt_show_inline_target_mcp_returns_rows` |
| 10 | MCP exposes only the allowlist, queries are `mcp_reader` reads | `test_06_mcp.py::test_only_allowlisted_tools`, `test_mcp_session_read_only_as_mcp_reader`, `test_show_answers_top_browsers` |
| 11 | `dct render overview` succeeds with the right numbers | `test_07_dashboards.py::test_overview_board_renders`, `test_words_board_renders_with_superset_link` |
| 11 | Charts and Superset endpoints return 200 | `test_07_dashboards.py::test_charts_http_endpoints`, `test_superset_health` |

Beyond the plan: grants for `web_writer`, `el_loader` and `dbt_runner`, the
`updated_at` trigger, the Superset import and chart data API, the secret grep
over the Superset bundle, the CSP headers, and the documented
`show --select` denial.

dbt 2.0.8 unit tests on ClickHouse do not flag mismatches in boolean or NULL
expectations (found in M10), so those checks live in e2e.

### Gaps found and filled in M9

- Assert 1 had no explicit migrations check in the health stage.
- Assert 2 checked rows per sample but not the 3/2/1 mix.
- Assert 10 proved reader SELECT only on a probe table, not on the built marts.
- `test_reader_limits_are_enforced` ended in `or True` and asserted nothing.
  It now compares the effective settings.
