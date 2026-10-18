"""Message validation edge cases."""

import pytest
from web.validation import clean_message


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("hello", "hello"),
        ("  padded \n", "padded"),
        ("a" * 280, "a" * 280),
        ("ação café", "ação café"),
        ("line1\r\nline2", "line1\nline2"),
        (("x\r\n" * 139) + "x", ("x\n" * 139) + "x"),
    ],
)
def test_accepts(raw: str, expected: str) -> None:
    assert clean_message(raw, 280) == expected


@pytest.mark.parametrize(
    "raw", ["", "   ", "\n\t\r\n", "a" * 281, "a\x00b", " " + "a" * 281]
)
def test_rejects(raw: str) -> None:
    assert clean_message(raw, 280) is None


def test_limit_is_configurable() -> None:
    assert clean_message("abcd", 3) is None
    assert clean_message("abc", 3) == "abc"
