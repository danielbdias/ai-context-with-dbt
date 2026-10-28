"""Tests for the backdated sample data: no database needed."""

import csv
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from scripts.seed_history import HISTORY_DAYS, TRAFFIC_MIX, build_rows, copy_input

TODAY = date(2026, 10, 28)
SEEDS = Path("transform/dbt/seeds")


def mapped_families(filename: str) -> set[str]:
    with (SEEDS / filename).open() as handle:
        return {row["raw_family"] for row in csv.DictReader(handle)}


def test_rows_are_deterministic() -> None:
    assert build_rows(TODAY) == build_rows(TODAY)


def test_rows_cover_the_history_window_and_exclude_today() -> None:
    rows = build_rows(TODAY)
    earliest = datetime(2026, 10, 28, tzinfo=UTC) - timedelta(days=HISTORY_DAYS)
    assert min(row.created_at for row in rows) >= earliest
    assert max(row.created_at for row in rows) < datetime(2026, 10, 28, tzinfo=UTC)
    assert len({row.created_at.date() for row in rows}) == HISTORY_DAYS


def test_messages_fit_the_database_constraint() -> None:
    assert all(1 <= len(row.message.strip()) <= 280 for row in build_rows(TODAY))


def test_traffic_mix_uses_mapped_families_except_the_other_bucket() -> None:
    browsers, systems = (
        mapped_families("browser_family_map.csv"),
        mapped_families("os_family_map.csv"),
    )
    unmapped = {b for b, _, _ in TRAFFIC_MIX if b not in browsers}
    assert unmapped == {"Samsung Internet"}
    assert all(os_family in systems for _, os_family, _ in TRAFFIC_MIX)


def test_weekdays_are_busier_than_weekends() -> None:
    rows = build_rows(TODAY)
    weekday = [r for r in rows if r.created_at.weekday() < 5]
    weekend = [r for r in rows if r.created_at.weekday() >= 5]
    assert len(weekday) / 5 > len(weekend) / 2


def test_copy_input_is_one_tab_separated_line_per_row() -> None:
    rows = build_rows(TODAY)
    lines = copy_input(rows).splitlines()
    assert len(lines) == len(rows)
    assert all(line.count("\t") == 3 for line in lines)
    assert all("\\" not in row.message for row in rows)
