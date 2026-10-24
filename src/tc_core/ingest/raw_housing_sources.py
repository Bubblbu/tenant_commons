"""Raw sources for building housing facts (spec 2026-10-20, housing type),
stored verbatim and read by metrics/housing.py:

- raw_licences_2024: the City's 2024 rental licences by building type
  (business-licences-2013-to-2024, filtered at fetch to the addressed types:
  Apartment House, Rooming House, 99-year lease). No licensee names.
- raw_non_market: the City's non-market housing list with its unit counts by
  clientele (families = units with 2+ bedrooms, seniors = 55+, other = single
  non-seniors) and operator.
"""

from __future__ import annotations

import json
import sqlite3

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

RAW_LICENCES_2024_COLUMNS = ["licencenumber", "status", "businesstype", "house", "street", "geo_point_2d"]
RAW_NON_MARKET_COLUMNS = [
    "index_number", "name", "address", "project_status", "occupancy_year", "operator",
    "clientele_families", "clientele_seniors", "clientele_other", "url",
]


def ingest_raw_licences_2024(conn: sqlite3.Connection, path: str) -> int:
    df = conform_columns(
        normalize_cols(read_any_csv(path)), RAW_LICENCES_2024_COLUMNS,
        source="business-licences-2013-to-2024.csv", table="raw_licences_2024",
        columns_name="RAW_LICENCES_2024_COLUMNS",
    )
    return insert_rows(conn, "raw_licences_2024", df.with_columns(pl.col("house").cast(pl.String)))


def ingest_raw_non_market(conn: sqlite3.Connection, path: str) -> int:
    features = json.loads(open(path, encoding="utf-8").read())["features"]
    rows = [{c: f["properties"].get(c) for c in RAW_NON_MARKET_COLUMNS} for f in features]
    df = pl.DataFrame(rows, schema={c: pl.String for c in RAW_NON_MARKET_COLUMNS[:6]} | {
        "clientele_families": pl.Int64, "clientele_seniors": pl.Int64, "clientele_other": pl.Int64,
        "url": pl.String,
    }, strict=False)
    return insert_rows(conn, "raw_non_market", df)
