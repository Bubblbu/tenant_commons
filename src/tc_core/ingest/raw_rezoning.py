"""Ingest data/raw/cov_foi/rezoning_applications.csv verbatim into raw_rezoning.

Raw storage only — no name-key matching against buildings happens here.
Matching runs later in the same ingest, in `ingest/overlays.py`; see
raw_sro.py's docstring.
"""

from __future__ import annotations

import sqlite3

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

RENAME_MAP = {
    # The source's own ID (e.g. "RZ285"); distinct from raw_rezoning_id (our
    # PK). Note it is NOT reliably unique per row — a multi-site "umbrella"
    # application can cover two entirely different addresses as separate
    # rows (confirmed via a real duplicate-key collision, see overlays.py).
    "id": "source_id",
}

RAW_REZONING_COLUMNS = [
    "source_id",
    "name",
    "status",
    "category",
    "status_detail",
    "latitude",
    "longitude",
    "link",
]


def load_raw_rezoning_frame(path: str) -> pl.DataFrame:
    return conform_columns(
        normalize_cols(read_any_csv(path)),
        RAW_REZONING_COLUMNS,
        source="rezoning_applications.csv",
        table="raw_rezoning",
        columns_name="RAW_REZONING_COLUMNS",
        rename=RENAME_MAP,
    )


def ingest_raw_rezoning(conn: sqlite3.Connection, path: str) -> int:
    return insert_rows(conn, "raw_rezoning", load_raw_rezoning_frame(path))
