"""Bookkeeping for individual source runs — see `ingest_runs` in schema.sql.

One row per (run_id, source_name). Call `new_run_id()` once per full
`run_ingest()` invocation, then `record_run()` once per source, whether it
succeeded or failed — see `ingest/__init__.py::_run_source` for the wrapper
that does this around every source call.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone


def new_run_id() -> str:
    return uuid.uuid4().hex


def record_run(
    conn: sqlite3.Connection,
    run_id: str,
    source_name: str,
    *,
    started_at: str,
    status: str,
    row_count: int | None = None,
    error_message: str | None = None,
) -> None:
    finished_at = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO ingest_runs (
                run_id, source_name, started_at, finished_at, status,
                row_count, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, source_name, started_at, finished_at, status, row_count, error_message),
        )
