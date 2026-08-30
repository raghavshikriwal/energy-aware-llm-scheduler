"""SQLite persistence for scheduler comparison runs.

Stores a row per /api/compare call so past results can be reviewed later,
instead of every run being ephemeral and lost on refresh.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

DB_PATH: Path = Path("scheduler_runs.db")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS comparison_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    energy_savings_pct REAL NOT NULL,
    round_robin_total_wh REAL NOT NULL,
    energy_aware_total_wh REAL NOT NULL,
    round_robin_gpus_json TEXT NOT NULL,
    energy_aware_gpus_json TEXT NOT NULL
);
"""


@dataclass
class ComparisonRun:
    """A single stored comparison run, as read back from the database."""

    id: int
    created_at: str
    energy_savings_pct: float
    round_robin_total_wh: float
    energy_aware_total_wh: float
    round_robin_gpus: list[dict]
    energy_aware_gpus: list[dict]


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection, ensuring the schema exists first."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(_CREATE_TABLE_SQL)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _duplicates_last_run(
    conn: sqlite3.Connection,
    energy_savings_pct: float,
    round_robin_total_wh: float,
    energy_aware_total_wh: float,
) -> bool:
    """Check whether the most recent stored run has identical numeric results.

    Repeated "Run Comparison" clicks with an unchanged GPU config produce
    the exact same numbers every time (the simulation is deterministic), so
    without this check the history table fills up with rows that are
    indistinguishable except for timestamp — which reads as a bug rather
    than as real usage. Comparing against only the single most recent row
    (not the whole table) is intentional: a genuinely repeated identical
    result later on, separated by other runs, is still worth keeping as a
    record of when the user re-tested that config.
    """
    last = conn.execute(
        """
        SELECT energy_savings_pct, round_robin_total_wh, energy_aware_total_wh
        FROM comparison_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    if last is None:
        return False

    return (
        last["energy_savings_pct"] == energy_savings_pct
        and last["round_robin_total_wh"] == round_robin_total_wh
        and last["energy_aware_total_wh"] == energy_aware_total_wh
    )


def save_comparison_run(
    energy_savings_pct: float,
    round_robin_total_wh: float,
    energy_aware_total_wh: float,
    round_robin_gpus: list[dict],
    energy_aware_gpus: list[dict],
) -> int | None:
    """Persist one comparison result. Returns the new row's id.

    Skips the insert (returning None) if this result is identical to the
    immediately preceding run, so back-to-back clicks on the same GPU
    config don't flood the history table with duplicate rows. See
    `_duplicates_last_run` for why only the *last* row is checked.
    """
    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        if _duplicates_last_run(
            conn, energy_savings_pct, round_robin_total_wh, energy_aware_total_wh
        ):
            return None

        cursor = conn.execute(
            """
            INSERT INTO comparison_runs (
                created_at, energy_savings_pct,
                round_robin_total_wh, energy_aware_total_wh,
                round_robin_gpus_json, energy_aware_gpus_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                energy_savings_pct,
                round_robin_total_wh,
                energy_aware_total_wh,
                json.dumps(round_robin_gpus),
                json.dumps(energy_aware_gpus),
            ),
        )
        return cursor.lastrowid


def get_recent_runs(limit: int = 20) -> list[ComparisonRun]:
    """Return the most recent comparison runs, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM comparison_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [
        ComparisonRun(
            id=row["id"],
            created_at=row["created_at"],
            energy_savings_pct=row["energy_savings_pct"],
            round_robin_total_wh=row["round_robin_total_wh"],
            energy_aware_total_wh=row["energy_aware_total_wh"],
            round_robin_gpus=json.loads(row["round_robin_gpus_json"]),
            energy_aware_gpus=json.loads(row["energy_aware_gpus_json"]),
        )
        for row in rows
    ]