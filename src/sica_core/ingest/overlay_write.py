"""Run overlay matching at ingest time and persist both of its outputs.

Matched records set flags and detail columns on the building they matched.
Records that matched nothing go to `overlay_housing` — a companion table, not
appended to `buildings`, so `COUNT(*) FROM buildings` stays meaningful and the
unmatched count remains a visible data-quality metric (see schema.sql).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

import pandas as pd

from .overlays import match_overlays

logger = logging.getLogger("sica_core.ingest.overlays")

# Every column match_overlays() initialises on the buildings frame. The single
# list of them: export.reconstruct_points imports it, and
# test_building_overlay_columns_match_what_the_matcher_produces pins it to the
# matcher and the buildings schema, so matcher output can't be silently lost.
BUILDING_OVERLAY_COLUMNS = [
    "is_coop",
    "coop_status",
    "coop_ownership_model",
    "coop_url",
    "housing_name",
    "is_sro",
    "sro_owner",
    "sro_operator",
    "sro_operator_group",
    "sro_ownership_group",
    "sro_occupancy_status",
    "sro_registered_rooms",
    "is_rezoning",
    "rezoning_status",
    "rezoning_status_group",
    "rezoning_category",
    "rezoning_status_detail",
    "rezoning_link",
]

# overlay_housing.is_coop/is_sro are NOT NULL DEFAULT 0 (schema.sql), but a
# record's `extras` dict (overlays.py::_add_extra_housing) only carries the
# flag for the source type(s) that actually produced it — a coop-only record
# has no "is_sro" key at all. Default those two to False so an explicit NULL
# is never bound against a NOT NULL column.
_BOOL_DEFAULT_COLUMNS = {"is_coop", "is_sro"}

_OVERLAY_HOUSING_COLUMNS = [
    "addr_key",
    "address",
    "housing_name",
    "local_area",
    "lat",
    "lon",
    "is_coop",
    "is_sro",
    "coop_status",
    "coop_ownership_model",
    "coop_url",
    "sro_owner",
    "sro_operator",
    "sro_operator_group",
    "sro_ownership_group",
    "sro_occupancy_status",
    "sro_registered_rooms",
    "source_row_ids",
]


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, dict):  # source_row_ids, stored as JSON like merge.py's
        return json.dumps(value, sort_keys=True)
    return value


def ingest_overlays(conn: sqlite3.Connection, boundary_path: str) -> int:
    buildings = pd.read_sql_query(
        "SELECT building_id, addr_key, address, lat, lon, local_area FROM buildings",
        conn,
    )
    result = match_overlays(conn, buildings, boundary_path)

    matched = result.matched
    updates = []
    for _, row in matched.iterrows():
        values = [_clean(row.get(col)) for col in BUILDING_OVERLAY_COLUMNS]
        updates.append((*values, int(row["building_id"])))

    set_sql = ", ".join(f"{col} = ?" for col in BUILDING_OVERLAY_COLUMNS)
    ingested_at = datetime.now(timezone.utc).isoformat()

    with conn:
        conn.executemany(
            f"UPDATE buildings SET {set_sql} WHERE building_id = ?", updates
        )
        # Rebuildable in its own right: a re-run replaces the whole set rather
        # than appending, so re-running ingest without a full init_db() stays
        # idempotent.
        conn.execute("DELETE FROM overlay_housing")
        if result.unmatched:
            rows = []
            for rec in result.unmatched:
                values = [
                    _clean(rec.get(col, False if col in _BOOL_DEFAULT_COLUMNS else None))
                    for col in _OVERLAY_HOUSING_COLUMNS
                ]
                rows.append(tuple(values) + (ingested_at,))
            placeholders = ", ".join(["?"] * (len(_OVERLAY_HOUSING_COLUMNS) + 1))
            columns_sql = ", ".join(_OVERLAY_HOUSING_COLUMNS + ["ingested_at"])
            conn.executemany(
                f"INSERT INTO overlay_housing ({columns_sql}) VALUES ({placeholders})",
                rows,
            )

    logger.info(
        "Overlays: %d buildings flagged, %d unmatched records stored",
        int(matched[["is_coop", "is_sro", "is_rezoning"]].any(axis=1).sum()),
        len(result.unmatched),
    )
    return len(result.unmatched)
