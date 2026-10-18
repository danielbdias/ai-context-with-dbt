# Agent guide: querying the marts

For AI agents (and people) who answer questions from this warehouse. Everything
you need is in the dbt project `transform/dbt/`. Read descriptions first, then
query the marts.

## The rule

Query only `{{ ref('mart_...') }}` (or `fct_submissions`) through
`dbt show --inline`. Readers (`mcp_reader`, `charts_reader`) can SELECT only
from the `marts` database. `raw` and `staging` are denied, and so is
`dbt show --select <non-mart model>`, which re-runs that model's SQL.

```bash
dbt show --inline "select browser, submissions_count, pct
                   from {{ ref('mart_browser_distribution') }}
                   order by submissions_count desc" --target mcp
```

- Do not put `LIMIT` in the SQL. `dbt show` appends its own limit and
  ClickHouse rejects two. Use the flag instead: `--limit 20` (`--limit -1` for
  all rows).
- ClickHouse SQL dialect. Use `count()`, `toDate()`, `argMax()`, `lengthUTF8()`.
- Prefer a small, specific query over `select *` on `fct_submissions`, which
  holds free-text messages.

## Marts and the questions they answer

| Model | Grain | Answers |
|---|---|---|
| `mart_browser_distribution` | one row per browser | top browsers, share of Chrome or Safari |
| `mart_os_distribution` | one row per OS | top operating systems, mobile (iOS and Android) share |
| `mart_browser_os_combinations` | one row per browser and OS pair | which browser on which OS is most common |
| `mart_submissions_daily` | one row per UTC day with submissions | submissions per day, running total |
| `mart_word_frequencies` | one row per distinct word | most used words (PT and EN stopwords removed, accents folded) |
| `fct_submissions` | one row per live submission | row-level questions, message text, counts by any dimension |

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
| Descriptions, columns, tests | `get_node_details_dev`, or `target/manifest.json` |
| Lineage | `get_lineage_dev` |
| List models | `dbt ls` |
| Rendered SQL of a model | `dbt compile --select <model>` (runs as the target user) |
| Browse docs | `task dbt:docs`, then http://127.0.0.1:8081 |

## Not available locally

- Semantic Layer tools (`list_metrics`, `query_metrics`, `dbt sl ...`): they
  need the dbt platform (`dbt_cloud.yml`).
- Discovery API tools: the dbt platform only.
- `execute_sql`: the dbt platform only. Use `show --inline`.

## Semantic YAML probe (plan risk R4)

Result: **parses, but cannot be validated or queried locally.**

- The legacy spec (top-level `semantic_models:` with `measures`) parses, with a
  `SemanticModelDeprecated` warning.
- The new spec parses cleanly and is what the project uses. It is in
  `models/marts/_marts.yml`: `semantic_model: {enabled: true}` and
  `agg_time_dimension` on `fct_submissions`, `entity` and `dimension` /
  `granularity` on its columns, and the top-level metric `submissions_count`
  (`type: simple`, `agg: count`). A MetricFlow time spine model,
  `metricflow_time_spine` (built with `numbers()`), sits next to it.
- Both land in `manifest.json` and `semantic_manifest.json`.
- dbt skips semantic manifest validation without `dbt_cloud.yml`
  (`DBT_ENGINE_NO_WARN_SEMANTIC_MANIFEST_VALIDATION=1` silences the notice in
  the `dbt` container) and `dbt sl list|query|validate` fail with
  `Missing project in dbt_cloud.yaml`. So the YAML documents intent for agents
  that read the manifest, but nothing here executes it.

## dbt v2 on ClickHouse: things learned in M6

- ADBC driver: baked into the image at build time
  (`dbt system install-drivers`, then only the ClickHouse driver is kept in
  `/opt/dbt-cache`). No volume and no network are needed at run time.
- Connection uses the HTTP port (8123), not the native one.
- Freshness: the built-in ClickHouse query returns `UInt32` epoch seconds that
  dbt then rejects. `macros/freshness.sql` overrides
  `clickhouse__collect_freshness` to return real timestamps.
- Descriptions must not contain a semicolon (`task dbt:coverage` checks it).
- Unit-test fixtures are typed `Nullable`, which ClickHouse arrays refuse, so
  `int_submission_tokens` wraps the message in `ifNull`.
- `dbt docs serve` exists (`task dbt:docs`).
