"""Ingest data/raw/cov_open_data/city-owned-properties.csv verbatim into
raw_city_owned_properties. Read by metrics/sector.py, which marks buildings
on City land (spec 2026-10-20)."""

from __future__ import annotations

import sqlite3

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

RAW_CITY_OWNED_COLUMNS = [
    "building_no", "sap_address", "geom", "geo_local_area", "land_coord", "type", "geo_point_2d",
]


def load_raw_city_owned_frame(path: str) -> pl.DataFrame:
    df = conform_columns(
        normalize_cols(read_any_csv(path)),
        RAW_CITY_OWNED_COLUMNS,
        source="city-owned-properties.csv",
        table="raw_city_owned_properties",
        columns_name="RAW_CITY_OWNED_COLUMNS",
    )
    # Land coordinates are 8-digit keys; type inference drops leading zeros.
    return df.with_columns(pl.col("land_coord").cast(pl.String).str.zfill(8))


def ingest_raw_city_owned(conn: sqlite3.Connection, path: str) -> int:
    return insert_rows(conn, "raw_city_owned_properties", load_raw_city_owned_frame(path))
