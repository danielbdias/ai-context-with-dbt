# Agent guide: querying the marts

For AI agents (and people) who answer questions from this warehouse. Everything
you need is in the dbt project `transform/dbt/`. Read descriptions first, then
ask for a metric, or query a mart.

## Pick the tool

| You want | Use | Why |
|---|---|---|
| A number the project already defines (a count, a share, a running total, growth) | **`query_metrics`** | One definition, so every agent gets the same answer, and MetricFlow writes the SQL |
| Something no metric covers, or the rows themselves | **`show`** over a mart | Free-form SQL, read-only |
| What exists, what it means | `list_metrics`, `get_node_details_dev`, `list` | Descriptions are written for you |

Try a metric first. `mobile_share`, `submissions_wow_growth` and the rolling
window are easy to get subtly wrong by hand.

## Metrics (Semantic Layer)

Served by the dbt platform. The tools need `DBT_HOST`, `DBT_TOKEN` and
`DBT_PROD_ENV_ID` ([semantic-layer.md](semantic-layer.md)). Metrics are defined
in `transform/dbt/models/marts/_marts.yml`, on `fct_submissions`.

| Metric | Type | Answers |
|---|---|---|
| `submissions_count` | simple | How many live submissions |
| `mobile_submissions` | simple, filtered | How many came from a phone (iOS or Android) |
| `chrome_submissions` | simple, filtered | How many used Chrome, desktop or mobile |
| `avg_message_length` | simple | Average characters per message |
| `mobile_share` | ratio | Fraction from phones, 0 to 1 |
| `cumulative_submissions` | cumulative | Running total since the first submission |
| `submissions_7d_rolling` | cumulative, 7-day window | Submissions in the trailing 7 days |
| `submissions_wow_growth` | derived | Percent change against 7 days earlier |

Slice any of them by `metric_time` (grain `day`, `week`, `month`, `quarter` or
`year`), `submission__browser`, `submission__os` and `submission__is_mobile`.
Dimension names are the entity, two underscores, then the dimension. There is
also a saved query, `daily_mobile_mix`.

### Calling `query_metrics`

`group_by` items have a `name`, a `type` (`dimension`, `time_dimension` or
`entity`) and, for time, a `grain`. `where` uses `{{ Dimension('...') }}`.
Real calls and what they returned on this data:

```json
{"metrics": ["submissions_count"],
 "group_by": [{"name": "submission__browser", "type": "dimension"}],
 "order_by": [{"name": "submissions_count", "descending": true}], "limit": 3}
```
```text
[{"SUBMISSION__BROWSER": "Chrome", "SUBMISSIONS_COUNT": 312},
 {"SUBMISSION__BROWSER": "Safari", "SUBMISSIONS_COUNT": 119},
 {"SUBMISSION__BROWSER": "Firefox", "SUBMISSIONS_COUNT": 60}]
```

```json
{"metrics": ["mobile_share"],
 "group_by": [{"name": "metric_time", "type": "time_dimension", "grain": "month"}],
 "order_by": [{"name": "metric_time", "grain": "month"}]}
```
```text
[{"METRIC_TIME__MONTH": "2026-08-01", "MOBILE_SHARE": 0.222},
 {"METRIC_TIME__MONTH": "2026-09-01", "MOBILE_SHARE": 0.327},
 {"METRIC_TIME__MONTH": "2026-10-01", "MOBILE_SHARE": 0.368}]
```

```json
{"metrics": ["mobile_submissions"],
 "where": "{{ Dimension('submission__browser') }} = 'Chrome'"}
```
```text
[{"MOBILE_SUBMISSIONS": 92}]
```

Result keys are upper case, because Snowflake folds names.

### Gotchas

- **Dates after the last data.** The time spine runs for 3650 days from
  2024-01-01. Cumulative and rolling metrics return a row for every date in the
  range you ask for, so a query ordered by `metric_time` descending starts in
  the future (`submissions_7d_rolling` for a day after the last submission still
  counts the trailing window). Add a `where` on `metric_time`, for example
  `{{ TimeDimension('metric_time', 'day') }} <= '2026-10-28'`, or a `limit`.
  With that filter, `submissions_7d_rolling` for 2026-10-28 is 83, the same
  as a plain window query over the mart.
- **Today is partial.** The latest day has fewer rows than it will end up with,
  so `submissions_wow_growth` for today looks like a drop.
- **Fresh data needs a job.** The Semantic Layer serves what the last dbt
  platform production run built. After `task el`, run `task dbt:build` and the
  production job, or `show` and `query_metrics` can disagree for a while.
- **Days are UTC.** `created_date` is the UTC day of `created_at`.
- `get_metrics_compiled_sql` shows the SQL MetricFlow would run, which helps
  when a number looks wrong.

## Querying a mart with `show`

Query only `{{ ref('mart_...') }}` (or `fct_submissions`) through
`dbt show --inline`. Readers (`MCP_READER`, `CHARTS_READER`) can `SELECT` only
from the `MARTS` schema. `RAW` and `STAGING` are denied, and so is
`dbt show --select <non-mart model>`, which re-runs that model's SQL.

```bash
dbt show --inline "select browser, submissions_count, pct
                   from {{ ref('mart_browser_distribution') }}
                   order by submissions_count desc" --target mcp
```

- Do not put `LIMIT` in the SQL. `dbt show` appends its own limit. Use the flag
  instead: `--limit 20` (`--limit -1` for all rows).
- Snowflake SQL. Use `count(*)`, `max_by()`, `convert_timezone()`, `length()`,
  `qualify`. Column names come back upper case (`BROWSER`).
- Prefer a small, specific query over `select *` on `fct_submissions`, which
  holds free-text messages.

### Through MCP (Claude)

The dbt MCP server (`mcp/README.md`) exposes the same thing as the `show` tool.
Pass the SQL as `sql_query` and the row cap as `limit` (default 5):

```json
{"sql_query": "select browser, submissions_count, pct from {{ ref('mart_browser_distribution') }} order by submissions_count desc", "limit": 10}
```

It returns JSON rows, for example
`[{"BROWSER":"Chrome","SUBMISSIONS_COUNT":312,"PCT":58.65}, ...]`. Same rules:
no `LIMIT` in the SQL (if the word appears, the tool drops its own cap), and
only marts. Other tools: `list`, `get_node_details_dev` (`node_id`),
`get_lineage_dev` (`unique_id` such as `model.aictx.mart_browser_distribution`),
`compile`, `parse`.

## Marts and the questions they answer

| Model | Grain | Answers |
|---|---|---|
| `mart_browser_distribution` | one row per browser | top browsers, share of Chrome or Safari |
| `mart_os_distribution` | one row per OS | top operating systems, mobile (iOS and Android) share |
| `mart_browser_os_combinations` | one row per browser and OS pair | which browser on which OS is most common |
| `mart_submissions_daily` | one row per UTC day with submissions | submissions per day, running total |
| `mart_word_frequencies` | one row per distinct word | most used words (PT and EN stopwords removed, accents folded) |
| `fct_submissions` | one row per live submission | row-level questions, message text, counts by any dimension. Also has `is_mobile` and `message_length` |

Value sets: browser is one of Chrome, Firefox, Safari, Edge, Opera, Other. OS is
one of Windows, macOS, Linux, iOS, Android, Other. Soft-deleted submissions are
excluded from every mart.

Example questions and queries:

| Question | Query |
|---|---|
| What are the top browsers? | `select browser, submissions_count from {{ ref('mart_browser_distribution') }} order by submissions_count desc` |
| How many submissions per day? | `select day, submissions_count, cumulative_submissions from {{ ref('mart_submissions_daily') }} order by day` |
| Top 10 words? | `select display_word, frequency from {{ ref('mart_word_frequencies') }} order by frequency desc` with `--limit 10` |
| Which pair is most common? | `select browser, os, submissions_count from {{ ref('mart_browser_os_combinations') }} order by popularity_rank` with `--limit 1` |

## Finding things out locally

| Need | Use |
|---|---|
| What can I ask for | `list_metrics`, `get_dimensions`, `get_dimension_values` |
| Descriptions, columns, tests | `get_node_details_dev`, or `target/manifest.json` |
| Lineage | `get_lineage_dev` |
| List models | `dbt ls` (MCP tool `list`) |
| Rendered SQL of a model | `dbt compile --select <model>` (runs as the target user) |
| Browse docs | `task dbt:docs`, then http://127.0.0.1:8081 |

## Not available

- Discovery API and Admin API tools, and `execute_sql`: not enabled. Use
  `show --inline`.
- `dbt sl ...` on the host and a local MetricFlow: metrics are served by the dbt
  platform only. Without `DBT_HOST`, `DBT_TOKEN` and `DBT_PROD_ENV_ID` the metric
  tools return an error and `show` still works.

## Things learned porting dbt to Snowflake

- ADBC driver: baked into the image at build time (`dbt system install-drivers`,
  then only the Snowflake and DuckDB drivers are kept in `/opt/dbt-cache`). The
  built-in adapter works in dbt 2.0.8.
- Snowflake has no `\p{L}` in regex. Words are matched with the Latin range
  `[a-zà-öø-ÿ]+`, because `[[:alpha:]]` splits "café" into "caf".
- No Unicode normalisation either, so `normalize_token` is a `translate()` table
  of accented Latin letters. Tokens and stopwords both go through it, which keeps
  matching symmetric.
- Raw timestamps are `TIMESTAMP_LTZ`, so a plain `::date` follows the session
  time zone. `created_date` is pinned with `convert_timezone('UTC', ...)`.
- `max_by` keeps a NULL winner, so a later un-delete wins the dedup. The
  ClickHouse `argMax` skipped NULLs and needed a tuple workaround. An e2e test
  pins the behaviour.
- `generate_schema_name` writes to the shared `STAGING` and `MARTS` only for
  the targets `dev`, `ci`, `mcp`, `charts` and `prod`. Any other target gets a
  prefixed schema. The platform production job must use the target name `prod`.
- Descriptions must not contain a semicolon (`task dbt:coverage` checks it).
  dbt v2 persists descriptions as SQL comments.
- `dbt docs serve` exists (`task dbt:docs`).

## Example MCP session

`task mcp:smoke` runs it without a GUI (`scripts/mcp_smoke.py`, the same
command Claude uses):

```text
tools: compile, get_dimension_values, get_dimensions, get_entities, get_lineage_dev, get_metrics_compiled_sql, get_node_details_dev, list, list_metrics, parse, query_metrics, show
Q: how many submissions are there? (Semantic Layer)
  submissions_count = 532, matches count(*) on the mart
Q: what are the top browsers?
  1. Chrome: 312 submissions (58.65%)
  2. Safari: 119 submissions (22.37%)
  3. Firefox: 60 submissions (11.28%)
```

The second question is the check that matters: the number from the Semantic Layer
(the dbt platform) equals a plain `count(*)` on the mart (local `show`).

Snowflake query history for that session, queried as an admin, shows only
`MCP_READER`, running selects on the marts:

```sql
SELECT start_time, query_type, query_text
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(USER_NAME => 'MCP_READER'))
ORDER BY start_time DESC LIMIT 20;
```
