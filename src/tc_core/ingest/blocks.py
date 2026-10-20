"""Ingest data/raw/cov_open_data/block-outlines.csv into raw_blocks."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..geometry import parse_geom
from ..io import normalize_cols, read_any_csv


def ingest_raw_blocks(conn: sqlite3.Connection, path: str) -> int:
    df = normalize_cols(read_any_csv(path))
    ingested_at = datetime.now(timezone.utc).isoformat()
    rows = [(raw_geom, ingested_at) for raw_geom in df["geom"] if parse_geom(raw_geom) is not None]
    with conn:
        conn.executemany("INSERT INTO raw_blocks (geom, ingested_at) VALUES (?, ?)", rows)
    return len(rows)
