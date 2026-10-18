"""User-Agent parsing: browser and OS families as returned by ua-parser."""

from typing import NamedTuple

from ua_parser import parse

UNKNOWN_FAMILY = "Other"


class Client(NamedTuple):
    """Browser and operating system families of a request."""

    browser_family: str
    os_family: str


def parse_user_agent(user_agent: str) -> Client:
    """Return ua-parser's families, or "Other" when it finds none.

    Values are stored as ua-parser reports them (for example "Mac OS X");
    dbt normalizes them downstream.
    """
    result = parse(user_agent)
    browser = result.user_agent.family if result.user_agent else UNKNOWN_FAMILY
    os_family = result.os.family if result.os else UNKNOWN_FAMILY
    return Client(browser or UNKNOWN_FAMILY, os_family or UNKNOWN_FAMILY)
