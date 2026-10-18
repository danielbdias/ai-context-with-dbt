"""Signed double-submit token behaviour."""

from web.csrf import is_signed, is_valid, issue_token

SECRET = "secret-a"


def test_issued_token_is_signed_and_unique() -> None:
    first, second = issue_token(SECRET), issue_token(SECRET)
    assert first != second
    assert is_signed(first, SECRET)


def test_matching_cookie_and_field_pass() -> None:
    token = issue_token(SECRET)
    assert is_valid(token, token, SECRET)


def test_missing_or_empty_values_fail() -> None:
    token = issue_token(SECRET)
    assert not is_valid(None, token, SECRET)
    assert not is_valid(token, None, SECRET)
    assert not is_valid("", "", SECRET)


def test_mismatch_fails() -> None:
    assert not is_valid(issue_token(SECRET), issue_token(SECRET), SECRET)


def test_forged_or_foreign_token_fails() -> None:
    foreign = issue_token("secret-b")
    assert not is_valid(foreign, foreign, SECRET)
    assert not is_valid("abc.def", "abc.def", SECRET)
    assert not is_valid("nodot", "nodot", SECRET)
    assert not is_valid("é.é", "é.é", SECRET)
