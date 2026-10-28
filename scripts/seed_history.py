"""Backfill about 60 days of sample submissions (`task seed:history`).

The web form can only create rows dated now, which leaves one day of data. This
inserts backdated rows straight into Postgres so the Semantic Layer has a
time series (cumulative, rolling and week-over-week metrics need one).

`created_at` is backdated, but `updated_at` keeps its default of now(). dlt's
incremental cursor is `updated_at`, so rows older than the stored cursor would
be skipped. Rows skip `request_metadata`: the warehouse never reads it.

It runs psql inside the compose `postgres` container (like `task psql`), never
through a host port: another Postgres on the host can shadow 127.0.0.1:5432.
Reads POSTGRES_ADMIN_PASSWORD. It does nothing if backdated rows already exist,
so it is safe to run twice.
"""

import os
import random
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

HISTORY_DAYS = 60
SEED = 42
# (ua-parser browser family, ua-parser OS family, weight). The families match
# transform/dbt/seeds. Samsung Internet is unmapped on purpose: it lands in Other.
TRAFFIC_MIX: tuple[tuple[str, str, int], ...] = (
    ("Chrome", "Windows", 22),
    ("Chrome", "Mac OS X", 14),
    ("Chrome Mobile", "Android", 18),
    ("Mobile Safari", "iOS", 16),
    ("Safari", "Mac OS X", 8),
    ("Firefox", "Windows", 6),
    ("Firefox", "Linux", 4),
    ("Edge", "Windows", 6),
    ("Opera", "Windows", 2),
    ("Chrome", "Linux", 3),
    ("Samsung Internet", "Android", 2),
)
MESSAGES: tuple[str, ...] = (
    "Adoro café com dados abertos, que bom",
    "The cafe near the office has great coffee",
    "Os dados de hoje mostram que o tempo muda",
    "Great talk about analytics and metrics",
    "Gostei muito da apresentação sobre contexto",
    "Semantic layers make metrics consistent",
    "Quero aprender mais sobre engenharia de dados",
    "Data quality matters more than dashboards",
    "Nosso pipeline roda toda manhã sem falhas",
    "Agents need good context to answer well",
    "Métricas claras ajudam a decidir melhor",
    "Loved the live demo, very clear",
    "O café estava ótimo durante o workshop",
    "Testing models early saves a lot of time",
    "Documentação boa vale ouro para o time",
    "Short and sweet",
)


class HistoryRow(NamedTuple):
    """One backdated submission."""

    message: str
    browser_family: str
    os_family: str
    created_at: datetime


def daily_volume(rng: random.Random, day_index: int, weekday: int) -> int:
    """Rows for one day: slow growth, busier weekdays, some noise.

    Args:
        rng: Seeded random source.
        day_index: 0 for the oldest day, increasing towards today.
        weekday: 0 for Monday up to 6 for Sunday.
    """
    base = 3 + day_index * 0.15
    factor = 0.6 if weekday >= 5 else 1.4
    return max(1, round(base * factor + rng.uniform(-1.5, 1.5)))


def build_rows(
    today: date, days: int = HISTORY_DAYS, seed: int = SEED
) -> list[HistoryRow]:
    """Deterministic rows for the `days` days before `today` (today excluded)."""
    rng = random.Random(seed)  # noqa: S311 - sample data, not security
    weights = [weight for _, _, weight in TRAFFIC_MIX]
    rows: list[HistoryRow] = []
    for day_index in range(days):
        day = today - timedelta(days=days - day_index)
        midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
        for _ in range(daily_volume(rng, day_index, day.weekday())):
            browser, os_family, _ = rng.choices(TRAFFIC_MIX, weights)[0]
            seconds = int(rng.triangular(0, 86_399, 14 * 3600))
            rows.append(
                HistoryRow(
                    rng.choice(MESSAGES),
                    browser,
                    os_family,
                    midnight + timedelta(seconds=seconds),
                )
            )
    return rows


def run_psql(sql: str, stdin: str | None = None) -> str:
    """Run one statement as the admin in the `postgres` container; return stdout."""
    command = [
        "docker", "compose", "exec", "-T",
        "-e", f"PGPASSWORD={os.environ['POSTGRES_ADMIN_PASSWORD']}",
        "postgres", "psql", "-U", "postgres", "-d", "app",
        "-v", "ON_ERROR_STOP=1", "-Atc", sql,
    ]  # fmt: skip
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        command, input=stdin, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def copy_input(rows: list[HistoryRow]) -> str:
    """Rows in COPY text format (tab separated). Values never contain tabs."""
    return "".join(
        f"{row.message}\t{row.browser_family}\t{row.os_family}"
        f"\t{row.created_at.isoformat()}\n"
        for row in rows
    )


def insert_rows(rows: list[HistoryRow]) -> int:
    """Insert rows unless backdated ones exist; return how many were inserted."""
    existing = int(
        run_psql(
            "SELECT count(*) FROM app.submissions"
            " WHERE created_at < now() - interval '1 day'"
        )
    )
    if existing:
        print(f"history already seeded ({existing} older rows), skipping")
        return 0
    run_psql(
        "COPY app.submissions (message, browser_family, os_family, created_at)"
        " FROM STDIN",
        copy_input(rows),
    )
    return len(rows)


def main() -> int:
    """Entry point: backfill the Postgres container of the dev stack."""
    inserted = insert_rows(build_rows(datetime.now(UTC).date()))
    print(f"inserted {inserted} rows over {HISTORY_DAYS} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
