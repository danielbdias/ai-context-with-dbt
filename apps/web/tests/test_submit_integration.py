"""Form handler against a real Postgres: transactions, audit rows, 429."""

import io
import logging
from collections.abc import Callable

import httpx
import psycopg
import pytest
from conftest import CLIENT, PASSWORD
from fastapi.testclient import TestClient
from web.auth import hash_ip
from web.logs import LOGGER_NAME, JsonFormatter

MakeClient = Callable[..., TestClient]
pytestmark = pytest.mark.integration

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"


def post(
    client: TestClient,
    message: str,
    password: str = PASSWORD,
    send_csrf: bool = True,
) -> httpx.Response:
    """Fetch the page for a CSRF token, then post the form."""
    client.get("/")
    cookie = client.cookies["csrf_token"]
    data = {"password": password, "message": message}
    if send_csrf:
        data["csrf_token"] = cookie
    return client.post(
        "/",
        data=data,
        headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"},
        follow_redirects=False,
    )


def attempts(owner: psycopg.Connection, run_id: str) -> list[tuple[bool, str, int]]:
    return [
        (success, reason, sub_id)
        for success, reason, sub_id in owner.execute(
            "SELECT success, reason, submission_id FROM app.auth_attempts"
            " WHERE ip_hash = %s ORDER BY id",
            (hash_ip(CLIENT[0], run_id),),
        ).fetchall()
    ]


def test_healthz(make_client: MakeClient) -> None:
    assert make_client().get("/healthz").json() == {"status": "ok"}


def test_correct_password_writes_three_rows(
    make_client: MakeClient, owner: psycopg.Connection, run_id: str
) -> None:
    response = post(make_client(), f"{run_id} olá café")
    assert response.status_code == 303
    assert response.headers["location"] == "/?ok=1"
    sub = owner.execute(
        "SELECT id, browser_family, os_family FROM app.submissions WHERE message = %s",
        (f"{run_id} olá café",),
    ).fetchall()
    assert [(b, o) for _, b, o in sub] == [("Firefox", "Linux")]
    meta = owner.execute(
        "SELECT user_agent_raw, ip_hash, accept_language"
        " FROM app.request_metadata WHERE submission_id = %s",
        (sub[0][0],),
    ).fetchall()
    assert meta == [(UA, hash_ip(CLIENT[0], run_id), "pt-BR,pt;q=0.9")]
    assert attempts(owner, run_id) == [(True, "ok", sub[0][0])]


def test_wrong_password_only_audits(
    make_client: MakeClient, owner: psycopg.Connection, run_id: str
) -> None:
    response = post(make_client(), f"{run_id} nope", password="bad")
    assert response.status_code == 401
    assert attempts(owner, run_id) == [(False, "bad_password", None)]
    count = owner.execute(
        "SELECT count(*) FROM app.submissions WHERE message LIKE %s",
        (f"{run_id}%",),
    ).fetchone()
    assert count == (0,)


@pytest.mark.parametrize("message", ["", "   ", "x" * 281])
def test_invalid_input_is_400(
    make_client: MakeClient, owner: psycopg.Connection, run_id: str, message: str
) -> None:
    assert post(make_client(), message).status_code == 400
    assert attempts(owner, run_id) == [(False, "invalid_input", None)]


def test_missing_csrf_is_403(
    make_client: MakeClient, owner: psycopg.Connection, run_id: str
) -> None:
    response = post(make_client(), f"{run_id} hi", send_csrf=False)
    assert response.status_code == 403
    assert attempts(owner, run_id) == [(False, "csrf", None)]


def test_rate_limit_returns_429_after_n_failures(
    make_client: MakeClient, owner: psycopg.Connection, run_id: str
) -> None:
    client = make_client(rate_limit_max=3)
    codes = [post(client, f"{run_id} a", password="bad").status_code for _ in range(3)]
    assert codes == [401, 401, 401]
    blocked = post(client, f"{run_id} a")  # correct password is refused too
    assert blocked.status_code == 429
    reasons = [reason for _, reason, _ in attempts(owner, run_id)]
    assert reasons == ["bad_password"] * 3 + ["rate_limited"]


def test_rate_limit_window_expires(
    make_client: MakeClient, owner: psycopg.Connection, run_id: str
) -> None:
    client = make_client(rate_limit_max=1, rate_limit_window_seconds=1)
    assert post(client, f"{run_id} a", password="bad").status_code == 401
    assert post(client, f"{run_id} a").status_code == 429
    owner.execute(
        "UPDATE app.auth_attempts SET attempted_at = now() - interval '1 hour'"
        " WHERE ip_hash = %s",
        (hash_ip(CLIENT[0], run_id),),
    )
    assert post(client, f"{run_id} a").status_code == 303


def test_logs_never_contain_message_or_password(
    make_client: MakeClient, run_id: str
) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    client = make_client()
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    try:
        post(client, f"{run_id} secret-body", password="hunter2")
        post(client, f"{run_id} secret-body")
    finally:
        logger.removeHandler(handler)
    out = stream.getvalue()
    assert "request_id" in out
    assert "secret-body" not in out
    assert "hunter2" not in out
