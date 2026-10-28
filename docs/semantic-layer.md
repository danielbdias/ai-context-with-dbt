# Semantic Layer on the dbt platform

The demo defines its metrics in `transform/dbt/models/marts/_marts.yml`, but
nothing can query them locally. The Semantic Layer API, and the dbt-mcp tools
that call it (`list_metrics`, `query_metrics`, ...), are served by the dbt
platform from a successful production run. This guide sets that up once.

> The platform ignores `transform/dbt/profiles.yml`. Its connection, roles and
> warehouses are set in the UI, using the same values `infra/snowflake/setup.sql`
> created.

## Before you start

- A dbt platform account on **Starter, Enterprise or Enterprise+** with a
  Developer seat. Snowflake is a supported Semantic Layer warehouse.
- `task snowflake:setup`, `task el` and `task dbt:build` already ran, so the
  `AICTX` database has data and the roles exist.
- The repo is on GitHub and the dbt GitHub app can read it.
- If your Snowflake account has a **network policy**, allow the dbt platform IP
  addresses for your region, or the connection fails. See
  [access regions and IP addresses](https://docs.getdbt.com/docs/platform/about-platform/access-regions-ip-addresses).

## 1. Create the project

1. **Account settings > Projects > New project**, name it `aictx`.
2. Connection: **Snowflake**.

   | Field | Value |
   |---|---|
   | Account | `SNOWFLAKE_ACCOUNT` from `.env` (`orgname-accountname`) |
   | Database | `AICTX` |
   | Warehouse | `AICTX_TRANSFORM_WH` |

3. Repository: connect this repo through the GitHub app.
4. The dbt project is in `transform/dbt`, not the repo root. Set the project
   subdirectory to `transform/dbt`. I could not confirm the exact label in the
   docs, so look for a "project subdirectory" field in the project settings.

## 2. Production environment

**Orchestration > Environments > Create environment**, type **Deployment**,
and mark it as the **production** environment.

| Setting | Value |
|---|---|
| dbt version | the **v2 Stable** release track (see the note below) |
| Role | `AICTX_DBT_RUNNER` |
| Database | `AICTX` |
| Warehouse | `AICTX_TRANSFORM_WH` |

Connection profile (credentials):

| Field | Value |
|---|---|
| Auth | Username and password |
| Username | `DBT_RUNNER` |
| Password | `SNOWFLAKE_DBT_RUNNER_PASSWORD` from `.env` |
| Schema | `staging` |

dbt v2 is generally available on the platform for Snowflake. If **v2 Stable**
is not in the release track list, ask your dbt Labs account team about
eligibility, or enable it from **Account settings > Account > Enable dbt v2
readiness & upgrade features**. This project already builds on dbt 2.0.8.

## 3. Production job

**Create job > Deploy job**:

| Setting | Value |
|---|---|
| Job name | `Daily build` |
| Commands | `dbt build` (the default) |
| Run source freshness | on |
| Target name | **`prod`** (under **Advanced settings**) |

The target name matters. `generate_schema_name`
(`transform/dbt/macros/generate_schema_name.sql`) writes to the shared `STAGING`
and `MARTS` schemas only for the targets `dev`, `ci`, `mcp`, `charts` and
`prod`. Any other name, including the platform default, builds into a prefixed
schema such as `staging_marts`, and the Semantic Layer would not find the tables
the readers can see.

A job builds the branch its environment points at, which is `main` by default.
While the Snowflake migration is still in open pull requests, `main` has the
ClickHouse SQL and the job fails with errors such as `unexpected '('` in
`metricflow_time_spine.sql`. Either merge the migration into `main` first, or
turn on the environment's custom branch setting (look for **Only run on a custom
branch** in the environment settings) and give it the migration branch.

Click **Run now** and wait for a successful run. The Semantic Layer cannot be
configured until the environment has one.

For developing in the Studio IDE, leave the target name at its default. Your
builds then go to `<your schema>_staging` and `<your schema>_marts`, and cannot
overwrite the shared marts.

## 4. Enable the Semantic Layer

1. **Account settings > Projects >** your project **> Semantic Layer >
   Configure Semantic Layer**.
2. Pick the production deployment environment and **Save**.
3. **Add Semantic Layer credential**. Use read-only credentials, because these
   run the queries the Semantic Layer issues:

   | Field | Value |
   |---|---|
   | Role | `AICTX_MCP_READER` |
   | Warehouse | `AICTX_READ_WH` |
   | Username | `MCP_READER` |
   | Password | `SNOWFLAKE_MCP_READER_PASSWORD` from `.env` |

   `AICTX_MCP_READER` can read `MARTS` only, and its warehouse caps each query at
   30 seconds. That is the same guardrail the local MCP server uses.
4. **Map new service token**. Name it `aictx-mcp` and select the permission sets
   **Semantic Layer Only** and **Metadata Only**, then **Save**. The token is
   shown once, so copy it now.

## 5. Collect the connection values

From the project's **Project details** page and your account:

| Value | Used as | Where |
|---|---|---|
| The Access URL without its first label, for example `us1.dbt.com` | `DBT_HOST` | **Account settings** (Access URLs). A bare hostname works, and so does `https://host` |
| The first label of the Access URL, for example `abc123` | `DBT_HOST_PREFIX` | Only for Access URLs shaped `<prefix>.<cell>.dbt.com`, such as `abc123.us1.dbt.com`. For `cloud.getdbt.com` set `DBT_HOST=cloud.getdbt.com` and leave this empty |
| Service token | `DBT_TOKEN` | step 4 |
| Production environment ID (a number, not the URL) | `DBT_PROD_ENV_ID` | **Project details**, or the number after `/environments/` in the environment's URL |
| Account ID | `DBT_ACCOUNT_ID` | only if you use a personal access token instead |

An Access URL of `abc123.us1.dbt.com` therefore becomes `DBT_HOST=us1.dbt.com`
and `DBT_HOST_PREFIX=abc123`. dbt's docs say the prefix is optional when
`DBT_HOST` already contains it. With dbt-mcp 2.7.0 and a token, it is not:
without `DBT_HOST_PREFIX` the Semantic Layer tools query
`semantic-layer.abc123.us1.dbt.com`, which does not exist (the log shows `Name or
service not known`). The real host is `abc123.semantic-layer.us1.dbt.com`.

Putting the full `abc123.us1.dbt.com` in `DBT_HOST` together with the prefix also
works, because dbt-mcp strips the duplicate, but it logs a warning on every
start. The split form calls the same endpoint without it.

Never commit these. The next change wires them into dbt-mcp through `.env`.

dbt's docs recommend a personal access token for the Semantic Layer tools,
because a service token only covers the toolsets its permission sets allow, and
`execute_sql` does not work with service tokens at all. A service token is fine
for this demo, which uses `list_metrics`, `get_dimensions` and `query_metrics`.

## Validate the definitions without the platform

Local `dbt parse` skips semantic validation (there is no `dbt_cloud.yml`), so a
broken metric only shows up once the platform job runs. Check it earlier with the
validator MetricFlow itself uses:

```bash
task dbt:parse
uv run --no-project --with dbt-semantic-interfaces python - <<'PY'
import json
from dbt_semantic_interfaces.implementations.semantic_manifest import PydanticSemanticManifest
from dbt_semantic_interfaces.validations.semantic_manifest_validator import SemanticManifestValidator
raw = json.load(open("transform/dbt/target/semantic_manifest.json"))
manifest = PydanticSemanticManifest.parse_obj(raw)
results = SemanticManifestValidator[PydanticSemanticManifest]().validate_semantic_manifest(manifest)
print("errors:", results.errors, "warnings:", results.warnings)
PY
```

Both lists should be empty. This is not `mf validate-configs`, which needs a
local MetricFlow install.

## What to expect

- The metrics from `_marts.yml` (`submissions_count`, `mobile_share`,
  `submissions_7d_rolling`, ...) appear once the production run succeeds and the
  Semantic Layer is configured.
- Querying works against **deployment** environments. Development querying is
  not available yet.
- Re-run the job after changing models or metrics, because the Semantic Layer
  serves what the last production run built.
- Re-run `task el` to bring new Postgres rows into `RAW`. The platform job only
  transforms.

## Sources

- [Set up the Semantic Layer](https://docs.getdbt.com/docs/use-dbt-semantic-layer/setup-sl)
- [Service tokens](https://docs.getdbt.com/docs/dbt-cloud-apis/service-tokens)
- [Deployment environments](https://docs.getdbt.com/docs/deploy/deploy-environments)
- [Deploy jobs](https://docs.getdbt.com/docs/deploy/deploy-jobs) and
  [custom target names](https://docs.getdbt.com/docs/build/custom-target-names)
- [Upgrade to dbt v2 on the platform](https://docs.getdbt.com/docs/dbt-versions/upgrade-dbt-platform-version)
- [Self-hosted dbt MCP](https://docs.getdbt.com/docs/dbt-ai/setup-local-mcp)
