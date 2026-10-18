"""Seed the running web app with sample submissions (`task seed`).

Reads `SEED_BASE_URL` (default http://127.0.0.1:$WEB_PORT) and `APP_PASSWORD`.
"""

import os
import re
import sys

import httpx

from scripts.e2e.payloads import SAMPLES, Sample

TOKEN_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
WRONG_PASSWORD = "definitely-wrong"  # noqa: S105


def fetch_csrf_token(client: httpx.Client) -> str:
    """GET the page; the client keeps the cookie, the form carries the token."""
    response = client.get("/")
    response.raise_for_status()
    match = TOKEN_PATTERN.search(response.text)
    if match is None:
        raise RuntimeError("csrf_token field not found on the page")
    return match.group(1)


def submit(client: httpx.Client, password: str, message: str) -> httpx.Response:
    """POST the form with a fresh CSRF token, without following redirects."""
    token = fetch_csrf_token(client)
    return client.post(
        "/",
        data={"password": password, "message": message, "csrf_token": token},
    )


def make_client(base_url: str, sample: Sample) -> httpx.Client:
    """Client that sends the sample's User-Agent and Accept-Language."""
    headers = {
        "User-Agent": sample.user_agent,
        "Accept-Language": sample.accept_language,
    }
    return httpx.Client(base_url=base_url, headers=headers, timeout=10)


def seed(base_url: str, password: str) -> bool:
    """Send the samples plus one wrong-password attempt; return True if all ok."""
    ok = True
    for sample in SAMPLES:
        with make_client(base_url, sample) as client:
            status = submit(client, password, sample.message).status_code
        print(f"{status} {sample.browser_family}/{sample.os_family}")
        ok &= status == 303
    with make_client(base_url, SAMPLES[0]) as client:
        status = submit(client, WRONG_PASSWORD, "this one is rejected").status_code
    print(f"{status} wrong password (expected 401)")
    return ok and status == 401


def main() -> int:
    """Entry point; the exit code is non-zero if any response was unexpected."""
    port = os.environ.get("WEB_PORT", "8000")
    base_url = os.environ.get("SEED_BASE_URL", f"http://127.0.0.1:{port}")
    return 0 if seed(base_url, os.environ["APP_PASSWORD"]) else 1


if __name__ == "__main__":
    sys.exit(main())
