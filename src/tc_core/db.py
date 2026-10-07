"""Connection and schema-loading helpers for the tc_core SQLite store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(path: str | Path) -> sqlite3.Connection:
    """Open a connection with foreign key enforcement turned on."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added to PERSISTENT tables after they first shipped. CREATE TABLE IF
# NOT EXISTS leaves an existing table as it was, so init_db adds them here.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "raw_manager_listings": [("status", "TEXT"), ("units", "INTEGER")],
    "raw_lotr_searches": [("result_count", "INTEGER"), ("searched_at", "TEXT")],
}


def add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns:
            if have and name not in have:  # a missing table is init_db's job
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_db(conn: sqlite3.Connection, schema_path: str | Path = SCHEMA_PATH) -> None:
    """Load the schema.

    Safe to call repeatedly: every table except `ownership_claims` is dropped
    and recreated (schema.sql's REBUILDABLE section), while `ownership_claims`
    uses `CREATE TABLE IF NOT EXISTS` and is never touched by a rebuild.
    PERSISTENT tables that gained columns get them added (_ADDED_COLUMNS).
    Standalone importers call add_missing_columns() for the same effect
    without a rebuild.
    """
    sql = Path(schema_path).read_text(encoding="utf-8")
    with conn:
        conn.executescript(sql)
        add_missing_columns(conn)
