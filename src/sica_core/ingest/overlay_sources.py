"""SQLite-backed inputs for the overlay matcher.

Replaces the CSV reads that `sica_mapping/data/overlays.py` did at render
time: the SRO/co-op/rezoning sources and buildings' secondary addresses all
already live in SQLite (raw_sro, raw_coops, raw_rezoning, raw_buildings), so
the matcher reads them from there instead of re-parsing the source files.

The neighbourhood boundaries are the one input still read from disk — they
come from `local-area-boundary.geojson`, which the fetcher already downloads
(see fetch/cov_open_data.py), and are a straight passthrough rather than
something derived into a table.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from ..normalize import addr_key_from_freeform


def _frame_or_none(conn: sqlite3.Connection, sql: str) -> pd.DataFrame | None:
    df = pd.read_sql_query(sql, conn)
    return None if df.empty else df


def load_sro_frame(conn: sqlite3.Connection) -> pd.DataFrame | None:
    return _frame_or_none(
        conn,
        """
        SELECT raw_sro_id, address, secondary_address, building_name, owner,
               operator, operator_group, ownership_group, occupancy_status,
               registered_rooms AS "#_registered_rooms", latitude, longitude
        FROM raw_sro
        """,
    )


def load_coops_frame(conn: sqlite3.Connection) -> pd.DataFrame | None:
    return _frame_or_none(
        conn,
        """
        SELECT raw_coop_id, title, address, lat, lon, status, ownership_model,
               website, read_more_url
        FROM raw_coops
        """,
    )


def load_rezoning_frame(conn: sqlite3.Connection) -> pd.DataFrame | None:
    return _frame_or_none(conn, "SELECT * FROM raw_rezoning")


def load_secondary_address_index(conn: sqlite3.Connection) -> dict[str, str]:
    """secondary-address addr_key -> owning building's own addr_key.

    A faithful port of `overlays.py::_load_secondary_address_index`, reading
    raw_buildings instead of buildings.csv (same rows — buildings.csv is
    raw_buildings' source). Keys go through the same addr_key_from_freeform
    the matcher uses elsewhere, split on ";" only. Feeds the co-op/SRO
    fallback for buildings the source lists under a different entrance.
    """
    df = pd.read_sql_query(
        "SELECT address, secondary_addresses FROM raw_buildings", conn
    )
    index: dict[str, str] = {}
    for primary, secs in zip(df["address"], df["secondary_addresses"]):
        if secs is None or (isinstance(secs, float) and pd.isna(secs)):
            continue
        secs = str(secs).strip()
        if not secs:
            continue
        primary_key = addr_key_from_freeform(primary)
        for sec_addr in secs.split(";"):
            sec_addr = sec_addr.strip()
            if not sec_addr:
                continue
            # First building to claim a given secondary address wins; a
            # genuine collision is a data question, not something to silently
            # pick a "better" side of here.
            index.setdefault(addr_key_from_freeform(sec_addr), primary_key)
    return index


def load_boundary_feature_collection(path: str | Path) -> dict:
    """Read local-area-boundary.geojson straight off disk (passthrough)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
