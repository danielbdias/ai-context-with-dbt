"""User-Agent parsing table."""

import pytest
from web.ua import Client, parse_user_agent

CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"
SAFARI_IOS = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        (CHROME_MAC, Client("Chrome", "Mac OS X")),
        (FIREFOX_LINUX, Client("Firefox", "Linux")),
        (SAFARI_IOS, Client("Mobile Safari", "iOS")),
        ("curl/8.4.0", Client("curl", "Other")),
        ("", Client("Other", "Other")),
        ("\x00\xff garbage", Client("Other", "Other")),
    ],
)
def test_parse_user_agent(user_agent: str, expected: Client) -> None:
    assert parse_user_agent(user_agent) == expected
