"""Smoke test for the `web` package."""

from web import package_name


def test_package_name() -> None:
    """The package imports and reports its name."""
    assert package_name() == "web"
