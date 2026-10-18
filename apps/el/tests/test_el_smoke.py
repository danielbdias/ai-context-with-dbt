"""Smoke test for the `el` package."""

from el import package_name


def test_package_name() -> None:
    """The package imports and reports its name."""
    assert package_name() == "el"
