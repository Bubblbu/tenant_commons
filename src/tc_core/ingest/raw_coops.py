"""Ingest data/raw/chf_bc/coops_vancouver.csv (see scripts/fetch_coops.py) verbatim into raw_coops.

Raw storage only — no address-key matching against buildings happens here.
Matching runs later in the same ingest, in `ingest/overlays.py`; see
raw_sro.py's docstring.
"""

from __future__ import annotations

import sqlite3

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

RENAME_MAP = {
    "id": "source_id",  # the source's own ID; distinct from raw_coop_id (our PK)
}

RAW_COOPS_COLUMNS = [
    "source_id",
    "title",
    "city",
    "region",
    "neighbourhood",
    "school_district",
    "address",
    "lat",
    "lon",
    "status",
    "ownership_model",
    "bedrooms_min",
    "bedrooms_max",
    "home_types",
    "features",
    "summary",
    "featured_image",
    "website",
    "read_more_url",
]


def load_raw_coops_frame(path: str) -> pl.DataFrame:
    return conform_columns(
        normalize_cols(read_any_csv(path)),
        RAW_COOPS_COLUMNS,
        source="coops_vancouver.csv",
        table="raw_coops",
        columns_name="RAW_COOPS_COLUMNS",
        rename=RENAME_MAP,
    )


def ingest_raw_coops(conn: sqlite3.Connection, path: str) -> int:
    return insert_rows(conn, "raw_coops", load_raw_coops_frame(path))
