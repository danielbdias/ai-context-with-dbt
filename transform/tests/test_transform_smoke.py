"""Smoke test for the `transform` package."""

from transform import package_name


def test_package_name() -> None:
    """The package imports and reports its name."""
    assert package_name() == "transform"
