"""Page rendering, cookie flags and security headers (no database needed)."""

import pytest
from fastapi.testclient import TestClient
from web.main import create_app
from web.settings import Settings


@pytest.fixture
def client() -> TestClient:
    settings = Settings(
        app_password="pw",  # type: ignore[arg-type]
        csrf_secret="csrf",  # type: ignore[arg-type]
        ip_salt="salt",  # type: ignore[arg-type]
        postgres_web_writer_password="x",  # type: ignore[arg-type]
    )
    return TestClient(create_app(settings))


def test_page_content(client: TestClient) -> None:
    html = client.get("/").text
    assert "DEMO ONLY" in html
    assert 'maxlength="280"' in html
    assert 'type="password"' in html
    assert "Thanks" not in html


def test_ok_flash(client: TestClient) -> None:
    assert "Thanks" in client.get("/?ok=1").text


def test_security_headers(client: TestClient) -> None:
    headers = client.get("/").headers
    assert headers["content-security-policy"] == "default-src 'self'"
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"
    assert len(headers["x-request-id"]) == 32


def test_csrf_cookie_flags_and_field_match(client: TestClient) -> None:
    response = client.get("/")
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert f'value="{client.cookies["csrf_token"]}"' in response.text


def test_existing_valid_cookie_is_reused(client: TestClient) -> None:
    client.get("/")
    second = client.get("/")
    assert "set-cookie" not in second.headers


def test_no_docs_endpoints(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
