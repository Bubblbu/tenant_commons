"""Ingest data/buildings.csv verbatim into raw_buildings.

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
from datetime import datetime, timezone

import pandas as pd

from ..io import normalize_cols, read_any_csv

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
    "year_built",
    "bsns_group",
    "bsns_name",
    "bsns_trade_name",
    "bsns_type",
    "bsns_subtype",
    "value_land",
    "value_bldg",
    "bldg_land_ratio",
    "value_per_unit",
    "zoning",
    "zoning_district",
    "zoning_classification",
    "name",
    "management",
    "n_issues",
    "issues_details",
    "notes",
    "prospect",
]


def _stringify_money(v: object) -> object:
    """Normalize a value_land/value_bldg cell to a clean TEXT-storage string.

    Accepts either historical shape (a "$35,407,000.00"-style string, or a
    plain number that pandas has already parsed to int/float) and returns a
    clean string with no currency formatting and no trailing ".0" on whole
    numbers. None/NaN passes through as None.
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    return str(v).strip()


def load_raw_buildings_frame(path: str) -> pd.DataFrame:
    df = normalize_cols(read_any_csv(path))
    df = df.rename(columns=RENAME_MAP)
    df = df.drop(columns=[c for c in IGNORED_COLUMNS if c in df.columns])

    unexpected = set(df.columns) - set(RAW_BUILDINGS_COLUMNS)
    if unexpected:
        raise RuntimeError(
            f"buildings.csv has columns with no raw_buildings mapping: {sorted(unexpected)}. "
            "Add them to RAW_BUILDINGS_COLUMNS/schema.sql or IGNORED_COLUMNS, don't drop silently."
        )

    for col in ("value_land", "value_bldg"):
        if col in df.columns:
            df[col] = df[col].apply(_stringify_money)

    for col in RAW_BUILDINGS_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[RAW_BUILDINGS_COLUMNS]


def ingest_raw_buildings(conn: sqlite3.Connection, path: str) -> int:
    df = load_raw_buildings_frame(path)
    ingested_at = datetime.now(timezone.utc).isoformat()
    rows = [
        (*(None if pd.isna(v) else v for v in row), ingested_at)
        for row in df.itertuples(index=False)
    ]
    placeholders = ", ".join(["?"] * (len(RAW_BUILDINGS_COLUMNS) + 1))
    columns_sql = ", ".join(RAW_BUILDINGS_COLUMNS + ["ingested_at"])
    with conn:
        conn.executemany(
            f"INSERT INTO raw_buildings ({columns_sql}) VALUES ({placeholders})",
            rows,
        )
    return len(rows)
