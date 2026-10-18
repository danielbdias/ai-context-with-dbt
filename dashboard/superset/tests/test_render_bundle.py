"""Unit tests for the Superset bundle renderer and the committed bundle."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from dashboard.superset.render_bundle import (
    BUNDLE_DIR,
    PLACEHOLDER,
    main,
    render_bundle,
)

DATABASE_YAML = "databases/ClickHouse_marts.yaml"
EXPECTED_FILES = {
    "metadata.yaml",
    DATABASE_YAML,
    "datasets/ClickHouse_marts/mart_word_frequencies_1.yaml",
    "charts/Word_cloud_1.yaml",
    "dashboards/Word_cloud_1.yaml",
}


def read_zip(path: Path) -> dict[str, str]:
    """Return every member of a ZIP as text, keyed by member name."""
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name).decode() for name in archive.namelist()}


def test_render_fills_the_password_url_encoded(tmp_path: Path) -> None:
    out = tmp_path / "bundle.zip"
    render_bundle(BUNDLE_DIR, "p@ss/w:rd", out)
    database = read_zip(out)[f"aictx_bundle/{DATABASE_YAML}"]
    assert "superset_reader:p%40ss%2Fw%3Ard@clickhouse:8123/marts" in database
    assert PLACEHOLDER not in database


def test_render_keeps_every_bundle_file_under_one_root(tmp_path: Path) -> None:
    out = tmp_path / "bundle.zip"
    render_bundle(BUNDLE_DIR, "secret", out)
    assert set(read_zip(out)) == {f"aictx_bundle/{name}" for name in EXPECTED_FILES}


def test_committed_bundle_holds_a_placeholder_and_no_password() -> None:
    joined = "\n".join(
        path.read_text(encoding="utf-8") for path in BUNDLE_DIR.rglob("*.yaml")
    )
    assert PLACEHOLDER in joined
    assert "XXXXXXXXXX" not in joined
    # The placeholder token itself contains "PASSWORD", so match the key form.
    assert "password:" not in joined.lower()
    assert "password=" not in joined.lower()


def test_main_requires_one_output_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["render_bundle.py"]) == 2
    assert "usage" in capsys.readouterr().err
