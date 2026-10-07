"""Ingest data/raw/cov_foi/sra_housing_combined.csv verbatim into raw_sro.

Raw storage only — no address-key matching against buildings happens here.
Matching runs later in the same ingest, in `ingest/overlays.py`
(`match_overlays()`, persisted by `overlay_write.py`), reading this table.
Keeping the source verbatim also makes it browsable from tc_core's SQLite
store (CLAUDE.md Q8b), same as raw_buildings/raw_addresses.
"""

from __future__ import annotations

import sqlite3

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

# Raw CSV header -> raw_sro column, for the two that don't already match
# after normalize_cols() (lowercase + spaces->underscores).
RENAME_MAP = {
    "id": "source_id",  # the source's own ID; distinct from raw_sro_id (our PK)
    "#_registered_rooms": "registered_rooms",
}

RAW_SRO_COLUMNS = [
    "source_id",
    "address",
    "building_name",
    "secondary_address",
    "area",
    "latitude",
    "longitude",
    "owner",
    "operator",
    "operator_group",
    "ownership_group",
    "registered_rooms",
    "occupancy_status",
    "match_method",  # upstream address-matching flag from whoever combined the source lists; kept verbatim, unused here
]


def load_raw_sro_frame(path: str) -> pl.DataFrame:
    return conform_columns(
        normalize_cols(read_any_csv(path)),
        RAW_SRO_COLUMNS,
        source="sra_housing_combined.csv",
        table="raw_sro",
        columns_name="RAW_SRO_COLUMNS",
        rename=RENAME_MAP,
    )


def ingest_raw_sro(conn: sqlite3.Connection, path: str) -> int:
    return insert_rows(conn, "raw_sro", load_raw_sro_frame(path))
