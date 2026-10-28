"""Stage 7: dbt Charts renders the boards on the per-run database.

Runs after stage 6, so the marts exist. The charts manifest is parsed into
target/e2e_charts (the dev target/charts is left alone), then the charts service
starts on it. Every number asserted is computed from Postgres or the marts, not
hard-coded.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from scripts.e2e.helpers import (
    DENIED,
    ENV,
    compose,
    pg_query,
    run_dbt,
    sf_query,
)

pytestmark = pytest.mark.usefixtures("e2e_database")

DASHBOARD = ("core", "dashboard")
CHARTS = f"http://127.0.0.1:{ENV['CHARTS_PORT']}"


def exec_charts(*args: str) -> str:
    """Run a command inside the running charts container and return stdout."""
    return compose(
        "exec", "-T", "-w", "/work/project", "charts", *args, profiles=DASHBOARD
    ).stdout


def render_board(name: str) -> str:
    """Render one board to HTML on stdout (`-o -`) inside the charts container."""
    return exec_charts(
        "dct", "render", f"charts/{name}.yml", "--format", "html", "-o", "-"
    )


@pytest.fixture(scope="module")
def dashboards() -> Iterator[None]:
    """Parse the e2e charts manifest, then start dbt Charts."""
    parsed = run_dbt(
        "parse", "--target", "charts", "--target-path", "target/e2e_charts"
    )
    assert parsed.returncode == 0, parsed.stdout + parsed.stderr
    compose("up", "-d", "--build", "--wait", "charts", profiles=DASHBOARD)
    yield


def test_overview_board_renders(dashboards: None) -> None:
    html = render_board("overview")
    total = pg_query("SELECT count(*) FROM app.submissions WHERE deleted_at IS NULL")
    kpi = html.split('data-chart-id="total_submissions"', 1)[1]
    kpi = kpi.split('data-chart-id="', 1)[0]
    assert f">{total[0][0]}<" in kpi
    for label in ("Chrome", "Firefox", "Safari", "Total submissions"):
        assert label in html, label


def test_words_board_renders(dashboards: None) -> None:
    html = render_board("words")
    assert "dados" in html
    assert "Superset" not in html


def test_charts_http_endpoints(dashboards: None) -> None:
    for path in ("/", "/overview/", "/words/"):
        assert httpx.get(CHARTS + path, timeout=10).status_code == 200, path


def test_charts_validate_against_the_warehouse(dashboards: None) -> None:
    """Every board query runs as charts_reader (advisory warnings are fine)."""
    result = compose(
        "exec",
        "-T",
        "-w",
        "/work/project",
        "charts",
        "dct",
        "validate",
        "--warehouse",
        profiles=DASHBOARD,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM RAW.SUBMISSIONS",
        "SELECT count(*) FROM STAGING.STG_APP__SUBMISSIONS",
        "SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY LIMIT 1",
        "INSERT INTO MARTS.MART_WORD_FREQUENCIES VALUES ('x', 'x', 1)",
    ],
)
def test_charts_reader_is_marts_only(sql: str) -> None:
    assert sf_query("SELECT count(*) FROM MARTS.MART_WORD_FREQUENCIES", "charts_reader")
    with pytest.raises(DENIED):
        sf_query(sql, "charts_reader")
