"""Ingest data/raw/cov_open_data/property-addresses.csv verbatim into raw_addresses."""

from __future__ import annotations

import sqlite3

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

RAW_ADDRESSES_COLUMNS = [
    "civic_number",
    "geo_local_area",
    "geom",
    "p_parcel_id",
    "pcoord",
    "site_id",
    "std_street",
    "note",
    "geo_point_2d",
]


def load_raw_addresses_frame(path: str) -> pl.DataFrame:
    return conform_columns(
        normalize_cols(read_any_csv(path)),
        RAW_ADDRESSES_COLUMNS,
        source="property_addresses.csv",
        table="raw_addresses",
        columns_name="RAW_ADDRESSES_COLUMNS",
    )


def ingest_raw_addresses(conn: sqlite3.Connection, path: str) -> int:
    return insert_rows(conn, "raw_addresses", load_raw_addresses_frame(path))
