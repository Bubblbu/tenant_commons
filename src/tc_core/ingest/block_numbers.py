"""Ingest data/raw/cov_open_data/block-numbers.csv verbatim into raw_block_numbers."""

from __future__ import annotations

import sqlite3

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

RAW_BLOCK_NUMBERS_COLUMNS = [
    "label",
    "geo_local_area",
    "geom",
    "geo_point_2d",
]


def load_raw_block_numbers_frame(path: str) -> pl.DataFrame:
    return conform_columns(
        normalize_cols(read_any_csv(path)),
        RAW_BLOCK_NUMBERS_COLUMNS,
        source="block-numbers.csv",
        table="raw_block_numbers",
        columns_name="RAW_BLOCK_NUMBERS_COLUMNS",
    )


def ingest_raw_block_numbers(conn: sqlite3.Connection, path: str) -> int:
    return insert_rows(conn, "raw_block_numbers", load_raw_block_numbers_frame(path))
