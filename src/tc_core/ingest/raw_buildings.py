"""Ingest data/derived/buildings.csv verbatim into raw_buildings.

value_land/value_bldg are kept as TEXT — historically the source mixed plain
numbers with "$35,407,000.00"-style strings (100% of pre-2026-08-07 West End
rows used the latter, an artifact of that subset having gone through a
separate hand path; 0% elsewhere). Since the vhd pipeline's 2026-08-07
refresh replaced that two-tier assembly with one uniform city-wide Open Data
pull, the whole column now arrives plain numeric — `_stringify_money()`
normalizes either shape to a clean string for storage; actual parsing to a
number happens at merge time (see ingest/merge.py::_parse_money).

`secondary_addresses`, `folio`, `zoning_district`, `zoning_classification`,
`bsns_subtype` arrived with that same refresh (see docs/DATA_SOURCES.md).
`n_pids`, `is_primary_address`, `bldg_land_ratio`, `value_per_unit` dropped
out of it — left in RAW_BUILDINGS_COLUMNS anyway (they just fill as NULL
going forward) since nothing downstream reads them and removing them buys
nothing.
"""

from __future__ import annotations

import sqlite3

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

# Raw CSV header -> raw_buildings column, for the handful that don't already
# match after normalize_cols() (lowercase + spaces->underscores).
RENAME_MAP = {
    "address_is_primary?": "is_primary_address",
    "prospect?": "prospect",
}

# Intentionally not persisted:
# - unnamed:_0: a row-number artifact from however this CSV was exported, not sourced data.
# - vtu_members / westend_inbox / vtu_main_inbox / vtu_building: a one-off artifact from
#   manually merging buildings.csv with a small organizing-status tracking sheet for a
#   handful of buildings, not a recurring data source. Organizing-status tracking belongs
#   in a dedicated organizer view (its own table, fed on its own cadence) later — not four
#   ad hoc columns bolted onto raw_buildings now.
IGNORED_COLUMNS = {
    "unnamed:_0",
    "vtu_members",
    "westend_inbox",
    "vtu_main_inbox",
    "vtu_building",
}

RAW_BUILDINGS_COLUMNS = [
    "local_area",
    "address",
    "secondary_addresses",
    "primary_address",
    "is_primary_address",
    "n_pids",
    "pid",
    "folio",
    "units",
    "building_source",
    "source_licences",
    "year_built",
    "bsns_group",
    "bsns_name",
    "bsns_trade_name",
    "bsns_type",
    "bsns_subtype",
    "bsns_year",
    "value_land",
    "value_bldg",
    "bldg_land_ratio",
    "value_per_unit",
    "zoning",
    "zoning_district",
    "zoning_classification",
    "name",
    "foi_name",
    "management",
    "n_issues",
    "issues_details",
    "notes",
    "prospect",
]


def _stringify_money(v: object) -> object:
    """Normalize a value_land/value_bldg cell to a clean TEXT-storage string.

    Accepts either historical shape (a "$35,407,000.00"-style string, or a
    plain number already parsed to int/float) and returns a clean string with
    no currency formatting and no trailing ".0" on whole numbers. None passes
    through as None.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    return str(v).strip()


def load_raw_buildings_frame(path: str) -> pl.DataFrame:
    df = conform_columns(
        normalize_cols(read_any_csv(path)),
        RAW_BUILDINGS_COLUMNS,
        source="buildings.csv",
        table="raw_buildings",
        columns_name="RAW_BUILDINGS_COLUMNS",
        rename=RENAME_MAP,
        ignored=IGNORED_COLUMNS,
    )
    return df.with_columns(
        pl.col("value_land", "value_bldg").map_elements(_stringify_money, return_dtype=pl.String)
    )


def ingest_raw_buildings(conn: sqlite3.Connection, path: str) -> int:
    return insert_rows(conn, "raw_buildings", load_raw_buildings_frame(path))
