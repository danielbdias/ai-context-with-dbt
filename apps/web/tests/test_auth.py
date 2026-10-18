"""Password check, IP pseudonymization and the rate-limit threshold."""

import re

import pytest
from web.auth import hash_ip, is_over_limit, truncate_ip, verify_password


def test_verify_password() -> None:
    assert verify_password("dssbr", "dssbr")
    assert not verify_password("dssbR", "dssbr")
    assert not verify_password("", "dssbr")
    assert not verify_password("dssbr é", "dssbr")


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("203.0.113.77", "203.0.113.0/24"),
        ("::ffff:203.0.113.77", "203.0.113.0/24"),
        ("2001:db8:1234:5678::1", "2001:db8:1234::/48"),
        ("testclient", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_truncate_ip(host: str | None, expected: str) -> None:
    assert truncate_ip(host) == expected


def test_hash_ip_groups_by_network_and_depends_on_salt() -> None:
    same = hash_ip("203.0.113.1", "salt") == hash_ip("203.0.113.200", "salt")
    other_net = hash_ip("203.0.114.1", "salt") == hash_ip("203.0.113.1", "salt")
    other_salt = hash_ip("203.0.113.1", "other") == hash_ip("203.0.113.1", "salt")
    assert same
    assert not other_net
    assert not other_salt


def test_hash_ip_is_64_hex_and_hides_address() -> None:
    digest = hash_ip("203.0.113.1", "salt")
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert "203.0.113" not in digest


@pytest.mark.parametrize(
    ("failures", "limit", "expected"),
    [(0, 5, False), (4, 5, False), (5, 5, True), (9, 5, True)],
)
def test_is_over_limit(failures: int, limit: int, expected: bool) -> None:
    assert is_over_limit(failures, limit) is expected
