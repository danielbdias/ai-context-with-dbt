"""Stage 3: the web app writes the right rows, and rejects what it must."""

from __future__ import annotations

import re

import httpx
import pytest

from scripts.e2e.helpers import ENV, pg_query, web_client
from scripts.e2e.payloads import SAMPLES, Sample
from scripts.seed import fetch_csrf_token, make_client, submit

PASSWORD = ENV["APP_PASSWORD"]
SQL_COUNTS = {
    "submissions": "SELECT count(*) FROM app.submissions",
    "request_metadata": "SELECT count(*) FROM app.request_metadata",
    "auth_attempts": "SELECT count(*) FROM app.auth_attempts",
    "failed": "SELECT count(*) FROM app.auth_attempts WHERE NOT success",
}


def counts() -> dict[str, int]:
    return {name: pg_query(sql)[0][0] for name, sql in SQL_COUNTS.items()}


def deltas(before: dict[str, int]) -> dict[str, int]:
    after = counts()
    return {name: after[name] - before[name] for name in before}


def base_client() -> httpx.Client:
    return web_client({"User-Agent": SAMPLES[0].user_agent})


def test_web_is_healthy() -> None:
    with web_client() as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        page = client.get("/")
    assert page.status_code == 200
    assert "DEMO ONLY" in page.text
    assert page.headers["content-security-policy"] == "default-src 'self'"
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.message[:20])
def test_good_submission_adds_one_row_per_table(sample: Sample) -> None:
    before = counts()
    with make_client(f"http://127.0.0.1:{ENV['WEB_PORT']}", sample) as client:
        response = submit(client, PASSWORD, sample.message)
    assert response.status_code == 303
    assert response.headers["location"] == "/?ok=1"
    assert deltas(before) == {
        "submissions": 1,
        "request_metadata": 1,
        "auth_attempts": 1,
        "failed": 0,
    }
    sub_id, browser, os_family = pg_query(
        "SELECT id, browser_family, os_family FROM app.submissions"
        " WHERE message = %s ORDER BY id DESC LIMIT 1",
        params=(sample.message,),
    )[0]
    assert (browser, os_family) == (sample.browser_family, sample.os_family)
    ua, ip_hash, language = pg_query(
        "SELECT user_agent_raw, ip_hash, accept_language"
        " FROM app.request_metadata WHERE submission_id = %s",
        params=(sub_id,),
    )[0]
    assert (ua, language) == (sample.user_agent, sample.accept_language)
    assert re.fullmatch(r"[0-9a-f]{64}", ip_hash)
    audit = pg_query(
        "SELECT success, reason FROM app.auth_attempts WHERE submission_id = %s",
        params=(sub_id,),
    )
    assert audit == [(True, "ok")]


def test_sample_mix_is_three_chrome_two_firefox_one_safari() -> None:
    """Assert 2: the fixed-UA fixtures land with the expected families."""
    rows = pg_query(
        "SELECT browser_family, os_family, count(*) FROM app.submissions"
        " GROUP BY 1, 2 ORDER BY 3 DESC"
    )
    assert rows == [
        ("Chrome", "Mac OS X", 3),
        ("Firefox", "Linux", 2),
        ("Mobile Safari", "iOS", 1),
    ]


def test_wrong_password_is_401_and_only_audited() -> None:
    before = counts()
    with base_client() as client:
        response = submit(client, "not-the-password", "should not be stored")
    assert response.status_code == 401
    assert deltas(before) == {
        "submissions": 0,
        "request_metadata": 0,
        "auth_attempts": 1,
        "failed": 1,
    }
    reason = pg_query("SELECT reason FROM app.auth_attempts ORDER BY id DESC LIMIT 1")
    assert reason == [("bad_password",)]


def test_missing_csrf_is_403() -> None:
    before = counts()
    with base_client() as client:
        response = client.post("/", data={"password": PASSWORD, "message": "no token"})
    assert response.status_code == 403
    assert deltas(before) == {
        "submissions": 0,
        "request_metadata": 0,
        "auth_attempts": 1,
        "failed": 1,
    }
    reason = pg_query("SELECT reason FROM app.auth_attempts ORDER BY id DESC LIMIT 1")
    assert reason == [("csrf",)]


def test_forged_csrf_is_403() -> None:
    before = counts()
    with base_client() as client:
        fetch_csrf_token(client)
        response = client.post(
            "/",
            data={"password": PASSWORD, "message": "forged", "csrf_token": "a.b"},
        )
    assert response.status_code == 403
    assert deltas(before)["submissions"] == 0


def test_message_over_280_chars_is_400() -> None:
    before = counts()
    with base_client() as client:
        response = submit(client, PASSWORD, "x" * 281)
    assert response.status_code == 400
    assert deltas(before) == {
        "submissions": 0,
        "request_metadata": 0,
        "auth_attempts": 1,
        "failed": 1,
    }
    reason = pg_query("SELECT reason FROM app.auth_attempts ORDER BY id DESC LIMIT 1")
    assert reason == [("invalid_input",)]
