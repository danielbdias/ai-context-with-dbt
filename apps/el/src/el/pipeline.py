"""dlt pipeline: Postgres `app.submissions` -> ClickHouse `raw.submissions`.

Only the `submissions` table is selected, incrementally on `updated_at` and
merged on `id`. dlt keeps its state in ClickHouse (`raw._dlt_pipeline_state`),
so the container is stateless: a fresh pipelines directory restores the cursor
from the destination.

dlt's ClickHouse destination writes to ONE database (`raw`). With no dataset
name the final table is `raw.submissions` and the merge staging tables are
`raw.stg___<table>` (see docs/grants-matrix.md).
"""

import logging
import sys
import tempfile
import time
from collections.abc import Callable

import dlt
from dlt.common.destination import Destination
from dlt.common.pipeline import LoadInfo
from dlt.extract.resource import DltResource
from dlt.pipeline.exceptions import PipelineStepFailed
from dlt.sources.sql_database import sql_table

from el.settings import Settings, clickhouse_credentials, postgres_url

LOGGER = logging.getLogger("el")
PIPELINE_NAME = "pg_to_ch"
SOURCE_SCHEMA = "app"
SOURCE_TABLE = "submissions"
CURSOR_COLUMN = "updated_at"
PRIMARY_KEY = "id"
STAGING_LAYOUT = "stg"


def build_resource(settings: Settings) -> DltResource:
    """Incremental, merge-on-id resource for the `submissions` table only."""
    return sql_table(
        postgres_url(settings),
        table=SOURCE_TABLE,
        schema=SOURCE_SCHEMA,
        incremental=dlt.sources.incremental(
            CURSOR_COLUMN, lag=settings.el_incremental_lag_seconds
        ),
        write_disposition="merge",
        primary_key=PRIMARY_KEY,
    )


def build_destination(settings: Settings) -> Destination:
    """ClickHouse destination (MergeTree) loading into the `raw` database."""
    return dlt.destinations.clickhouse(
        credentials=clickhouse_credentials(settings),
        staging_dataset_name_layout=STAGING_LAYOUT,
    )


def build_pipeline(settings: Settings, pipelines_dir: str) -> dlt.Pipeline:
    """Pipeline with no dataset name, so tables are not prefixed."""
    return dlt.pipeline(
        PIPELINE_NAME,
        destination=build_destination(settings),
        dataset_name=None,
        pipelines_dir=pipelines_dir,
    )


def run_once(settings: Settings, pipelines_dir: str) -> LoadInfo:
    """Extract, normalize and load once; raise if any job failed."""
    pipeline = build_pipeline(settings, pipelines_dir)
    info = pipeline.run(build_resource(settings))
    info.raise_on_failed_jobs()
    trace = pipeline.last_trace
    counts = trace.last_normalize_info.row_counts if trace else {}
    LOGGER.info("loaded: %s", info)
    LOGGER.info("rows extracted this run: %s", counts)
    return info


def with_retries[T](action: Callable[[], T], attempts: int, delay_seconds: float) -> T:
    """Call `action`, retrying dlt step failures up to `attempts` times."""
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except PipelineStepFailed as error:
            if attempt == attempts:
                raise
            LOGGER.warning(
                "attempt %d/%d failed in step %s, retrying in %.0fs",
                attempt,
                attempts,
                error.step,
                delay_seconds,
            )
            time.sleep(delay_seconds)
    raise AssertionError("unreachable: attempts must be >= 1")


def main() -> int:
    """Entry point; the exit code is non-zero if the load did not complete."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    settings = Settings()  # type: ignore[call-arg]
    with tempfile.TemporaryDirectory(prefix="dlt_pipelines_") as pipelines_dir:
        try:
            with_retries(
                lambda: run_once(settings, pipelines_dir),
                max(settings.el_max_attempts, 1),
                settings.el_retry_delay_seconds,
            )
        except Exception:
            LOGGER.error("EL failed", exc_info=True)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
