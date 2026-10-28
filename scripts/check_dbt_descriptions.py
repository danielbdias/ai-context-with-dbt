"""Fail when a dbt model, seed, source, column or metric lacks a description.

Reads `target/manifest.json` (run `dbt parse` first, see `task dbt:coverage`).
Semantic Layer parts count too: metrics, saved queries, semantic models and
their dimensions and entities, because agents pick metrics by description.
Descriptions must also not contain a semicolon: dbt v2 persists them as SQL
comments and a semicolon breaks the statement.

Usage: python -m scripts.check_dbt_descriptions [MANIFEST_PATH]
"""

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = Path("transform/dbt/target/manifest.json")
CHECKED_TYPES = {"model", "seed"}
SEMANTIC_SECTIONS = {
    "metrics": "metric",
    "saved_queries": "saved query",
    "semantic_models": "semantic model",
}
SEMANTIC_PARTS = ("dimensions", "entities")


def _problems(label: str, node: dict[str, Any]) -> Iterator[str]:
    """Yield a message for each description problem of one node and its columns."""
    items = [(label, node.get("description"))]
    items += [
        (f"{label}.{name}", column.get("description"))
        for name, column in node.get("columns", {}).items()
    ]
    for name, description in items:
        if not (description or "").strip():
            yield f"{name}: missing description"
        elif ";" in description:
            yield f"{name}: description contains a semicolon"


def find_problems(manifest: dict[str, Any]) -> list[str]:
    """Return every description problem found in a parsed manifest."""
    nodes = [
        (f"{node['resource_type']} {node['name']}", node)
        for node in manifest.get("nodes", {}).values()
        if node.get("resource_type") in CHECKED_TYPES
    ]
    sources = [
        (f"source {node['source_name']}.{node['name']}", node)
        for node in manifest.get("sources", {}).values()
    ]
    problems = [
        msg for label, node in nodes + sources for msg in _problems(label, node)
    ]
    return problems + _semantic_problems(manifest)


def _semantic_problems(manifest: dict[str, Any]) -> list[str]:
    """Description problems of metrics, saved queries and semantic models."""
    problems: list[str] = []
    for section, kind in SEMANTIC_SECTIONS.items():
        for node in manifest.get(section, {}).values():
            label = f"{kind} {node['name']}"
            problems += _problems(label, node)
            for part in SEMANTIC_PARTS if section == "semantic_models" else ():
                for item in node.get(part, []):
                    problems += _problems(f"{label}.{item['name']}", item)
    return problems


def main(argv: list[str]) -> int:
    """Check the manifest at argv[0] (or the default) and return an exit code."""
    path = Path(argv[0]) if argv else DEFAULT_MANIFEST
    problems = find_problems(json.loads(path.read_text()))
    for problem in problems:
        print(problem)
    total = len(problems)
    print(f"{'FAIL' if total else 'OK'}: {total} description problem(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
