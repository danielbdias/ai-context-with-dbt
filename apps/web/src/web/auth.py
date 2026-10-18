"""Password check, client IP pseudonymization and rate limiting."""

import hashlib
import hmac
import ipaddress

import psycopg

from web.db import count_recent_failures
from web.settings import Settings

IPV4_PREFIX = 24
IPV6_PREFIX = 48
UNKNOWN_CLIENT = "unknown"


def verify_password(candidate: str, expected: str) -> bool:
    """Compare passwords in constant time."""
    return hmac.compare_digest(candidate.encode(), expected.encode())


def truncate_ip(host: str | None) -> str:
    """Reduce an address to its /24 (IPv4) or /48 (IPv6) network.

    Anything that is not an IP address (or a missing client) maps to a single
    "unknown" bucket.
    """
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return UNKNOWN_CLIENT
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    prefix = IPV4_PREFIX if ip.version == 4 else IPV6_PREFIX
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def hash_ip(host: str | None, salt: str) -> str:
    """Return the HMAC-SHA256 (hex) of the truncated address, keyed by salt."""
    network = truncate_ip(host)
    return hmac.new(salt.encode(), network.encode(), hashlib.sha256).hexdigest()


def is_over_limit(failures: int, limit: int) -> bool:
    """Return True once `limit` failures have been recorded in the window."""
    return failures >= limit


def is_rate_limited(conn: psycopg.Connection, ip_hash: str, settings: Settings) -> bool:
    """Return True when this client exceeded the failed-login limit."""
    failures = count_recent_failures(conn, ip_hash, settings.rate_limit_window_seconds)
    return is_over_limit(failures, settings.rate_limit_max)
