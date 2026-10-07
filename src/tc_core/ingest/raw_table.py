"""Shared plumbing for the raw_<source>.py modules: each stores one source CSV
verbatim in its own raw_* table (CLAUDE.md Q8b), with the same column checks.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import polars as pl


def conform_columns(
    df: pl.DataFrame,
    columns: list[str],
    *,
    source: str,
    table: str,
    columns_name: str,
    rename: dict[str, str] | None = None,
    ignored: set[str] = frozenset(),
) -> pl.DataFrame:
    """Rename to the table's column names and select them in order, adding
    any the source lacks as NULL. A source column with no mapping fails the
    ingest rather than being dropped silently."""
    df = df.rename(rename or {}, strict=False).drop(ignored, strict=False)
    unexpected = set(df.columns) - set(columns)
    if unexpected:
        also = " or IGNORED_COLUMNS" if ignored else ""
        raise RuntimeError(
            f"{source} has columns with no {table} mapping: {sorted(unexpected)}. "
            f"Add them to {columns_name}/schema.sql{also}, don't drop silently."
        )
    missing = [pl.lit(None).alias(c) for c in columns if c not in df.columns]
    return df.with_columns(missing).select(columns)


def insert_rows(
    conn: sqlite3.Connection, table: str, df: pl.DataFrame, *, replace: bool = False
) -> int:
    """Insert every row, stamped with one ingested_at. `replace` empties the
    table first (for PERSISTENT tables that re-import their whole source)."""
    ingested_at = datetime.now(timezone.utc).isoformat()
    rows = [(*row, ingested_at) for row in df.iter_rows()]
    columns_sql = ", ".join([*df.columns, "ingested_at"])
    placeholders = ", ".join(["?"] * (df.width + 1))
    with conn:
        if replace:
            conn.execute(f"DELETE FROM {table}")
        conn.executemany(f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders})", rows)
    return len(rows)
