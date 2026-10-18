"""Stage 7: dbt Charts renders the boards and Superset serves the word cloud.

Runs after stage 6, so the marts exist. The charts manifest is parsed into
target/e2e_charts (the dev target/charts is left alone), then the dashboard
services start on it. Every number asserted is computed from Postgres or the
marts, not hard-coded.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import clickhouse_connect.driver.exceptions as chx
import httpx
import pytest

from scripts.e2e.helpers import (
    ENV,
    REPO_ROOT,
    ch_query,
    compose,
    pg_query,
    run_dbt,
    superset_client,
)

DASHBOARD = ("core", "dashboard")
BUNDLE_DIR = REPO_ROOT / "dashboard" / "superset" / "bundle"
CHARTS = f"http://127.0.0.1:{ENV['CHARTS_PORT']}"
SUPERSET = f"http://127.0.0.1:{ENV['SUPERSET_PORT']}"
ERRORS = (chx.DatabaseError, chx.OperationalError)


def ch_user(name: str) -> dict[str, str]:
    return {"user": name, "password": ENV[f"CLICKHOUSE_{name.upper()}_PASSWORD"]}


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
    """Parse the e2e charts manifest, then start dbt Charts and Superset."""
    parsed = run_dbt(
        "parse", "--target", "charts", "--target-path", "target/e2e_charts"
    )
    assert parsed.returncode == 0, parsed.stdout + parsed.stderr
    compose("up", "-d", "--build", "--wait", "charts", "superset", profiles=DASHBOARD)
    yield


def test_overview_board_renders(dashboards: None) -> None:
    html = render_board("overview")
    total = pg_query("SELECT count(*) FROM app.submissions WHERE deleted_at IS NULL")
    kpi = html.split('data-chart-id="total_submissions"', 1)[1]
    kpi = kpi.split('data-chart-id="', 1)[0]
    assert f">{total[0][0]}<" in kpi
    for label in ("Chrome", "Firefox", "Safari", "Total submissions"):
        assert label in html, label


def test_words_board_renders_with_superset_link(dashboards: None) -> None:
    html = render_board("words")
    assert "dados" in html
    link = f"127.0.0.1:{ENV['SUPERSET_PORT']}/login/?next="
    assert (
        link + f"http://127.0.0.1:{ENV['SUPERSET_PORT']}/superset/dashboard/word-cloud/"
        in html
    )


def test_charts_http_endpoints(dashboards: None) -> None:
    for path in ("/", "/overview/", "/words/"):
        assert httpx.get(CHARTS + path, timeout=10).status_code == 200, path


def test_superset_health(dashboards: None) -> None:
    assert httpx.get(SUPERSET + "/health", timeout=10).status_code == 200


def test_superset_dashboard_and_chart_imported(dashboards: None) -> None:
    client = superset_client()
    dashboard = client.get("/api/v1/dashboard/word-cloud")
    assert dashboard.status_code == 200
    assert dashboard.json()["result"]["published"] is True
    dashboard_id = dashboard.json()["result"]["id"]
    charts = client.get(f"/api/v1/dashboard/{dashboard_id}/charts")
    assert charts.status_code == 200
    names = {
        (c["slice_name"], c["form_data"]["viz_type"]) for c in charts.json()["result"]
    }
    assert ("Word cloud", "word_cloud") in names


def test_superset_chart_data_returns_rows(dashboards: None) -> None:
    client = superset_client()
    chart = client.get("/api/v1/chart/?q=(page_size:100)").json()["result"]
    word_chart = next(c for c in chart if c["slice_name"] == "Word cloud")
    detail = client.get(f"/api/v1/chart/{word_chart['id']}").json()["result"]
    params = json.loads(detail["params"])
    metric = params["metric"]
    query_context = {
        "datasource": {"id": detail["datasource_id"], "type": "table"},
        "force": False,
        "queries": [
            {
                "columns": [params["series"]],
                "metrics": [metric],
                "orderby": [[metric, False]],
                "filters": [],
                "row_limit": params["row_limit"],
                "extras": {"having": "", "where": ""},
                "time_range": "No filter",
            }
        ],
        "result_format": "json",
        "result_type": "full",
    }
    response = client.post("/api/v1/chart/data", json=query_context)
    assert response.status_code == 200, response.text
    result = response.json()["result"][0]
    assert result["status"] == "success", result["error"]
    expected = ch_query(
        "SELECT count(DISTINCT display_word) FROM marts.mart_word_frequencies"
    )
    assert result["rowcount"] == expected[0][0] > 0


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count() FROM raw.submissions",
        "SELECT count() FROM staging.stg_app__submissions",
        "SELECT count() FROM system.query_log",
        "INSERT INTO marts.mart_word_frequencies VALUES ('x', 1)",
    ],
)
def test_charts_reader_is_marts_only(sql: str) -> None:
    creds = ch_user("charts_reader")
    assert ch_query("SELECT count() FROM marts.mart_word_frequencies", **creds)
    with pytest.raises(ERRORS):
        ch_query(sql, **creds)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count() FROM marts.mart_browser_distribution",
        "SELECT count() FROM marts.mart_os_distribution",
        "SELECT count() FROM staging.stg_app__submissions",
        "SELECT count() FROM system.query_log",
    ],
)
def test_superset_reader_is_word_table_only(sql: str) -> None:
    creds = ch_user("superset_reader")
    assert ch_query("SELECT count() FROM marts.mart_word_frequencies", **creds)
    with pytest.raises(ERRORS):
        ch_query(sql, **creds)


def test_bundle_holds_no_secrets() -> None:
    secrets = [
        value
        for key, value in ENV.items()
        if "PASSWORD" in key or "SECRET" in key or "SALT" in key
    ]
    files = [path for path in BUNDLE_DIR.rglob("*") if path.is_file()]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        for secret in secrets:
            assert secret not in text, path.name
        assert "XXXXXXXXXX" not in text, path.name
