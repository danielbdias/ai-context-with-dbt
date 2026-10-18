"""Tests for the dbt description coverage check."""

from scripts.check_dbt_descriptions import find_problems


def model(description: str, column_description: str) -> dict:
    return {
        "resource_type": "model",
        "name": "m",
        "description": description,
        "columns": {"c": {"description": column_description}},
    }


def test_complete_manifest_has_no_problems() -> None:
    manifest = {"nodes": {"model.p.m": model("Grain.", "A column.")}}
    assert find_problems(manifest) == []


def test_missing_model_and_column_descriptions_are_reported() -> None:
    manifest = {"nodes": {"model.p.m": model("", "  ")}}
    assert find_problems(manifest) == [
        "model m: missing description",
        "model m.c: missing description",
    ]


def test_semicolon_is_reported() -> None:
    manifest = {"nodes": {"model.p.m": model("Grain; more.", "A column.")}}
    assert find_problems(manifest) == ["model m: description contains a semicolon"]


def test_sources_are_checked_and_tests_are_ignored() -> None:
    manifest = {
        "nodes": {"test.p.t": {"resource_type": "test", "name": "t"}},
        "sources": {
            "source.p.app.s": {"source_name": "app", "name": "s", "columns": {}}
        },
    }
    assert find_problems(manifest) == ["source app.s: missing description"]
