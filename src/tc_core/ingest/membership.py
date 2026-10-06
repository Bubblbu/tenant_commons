"""Ingest an explicit allow-list of columns from the raw NationBuilder export
(config's `vtu_raw` path, e.g. data/raw/nationbuilder/membership_full.csv).

`membership_full.csv` is a raw, un-anonymized 154-column NationBuilder export
(emails, phone, ethnicity, religion, donation history, marital status, ...).
The current v1 pipeline only ever reads an address column, `tag_list`, and
`updated_at`; nothing else from those 154 columns should ever become a row
in this database. `pd.read_csv(usecols=...)` enforces the allow-list at the
CSV-read layer itself — the other 150 columns never even become an in-memory
column, let alone a SQLite row.

The address column is hardcoded to `primary_address1`, not derived via a
substring search over column names. v1's `next(c for c in df.columns if
"address" in c)` only works today because `primary_address1` happens to be
first in column order — a reordered NationBuilder export would silently
start reading a different address column (there's no column literally named
"address"; candidates include address_address1, billing_address1,
mailing_address1, work_address1, user_submitted_address1) with no error.

Runs after ingest/merge.py — building_id resolution needs buildings.addr_key
already populated.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pandas as pd

from ..normalize import AddressMatcher, addr_key_from_freeform
from .overlay_sources import load_secondary_address_index

ALLOWED_MEMBERSHIP_COLUMNS = ["nationbuilder_id", "primary_address1", "tag_list", "updated_at"]


def load_membership_frame(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=ALLOWED_MEMBERSHIP_COLUMNS)
    df["addr_key"] = df["primary_address1"].fillna("").apply(addr_key_from_freeform)
    return df


def _building_id_by_addr_key(conn: sqlite3.Connection) -> dict[str, int]:
    lookup = pd.read_sql_query("SELECT building_id, addr_key FROM buildings", conn)
    return dict(zip(lookup["addr_key"], lookup["building_id"]))


def ingest_membership(conn: sqlite3.Connection, path: str) -> int:
    df = load_membership_frame(path)
    building_id_by_addr_key = _building_id_by_addr_key(conn)
    # A member at a building's secondary address ("488 W 41st Ave" on the
    # parcel of 458 W 41st Ave) belongs to that building.
    matcher = AddressMatcher(building_id_by_addr_key, aliases=load_secondary_address_index(conn))
    ingested_at = datetime.now(timezone.utc).isoformat()

    rows = []
    for row in df.itertuples(index=False):
        nationbuilder_id = None if pd.isna(row.nationbuilder_id) else str(row.nationbuilder_id)
        tag_list = None if pd.isna(row.tag_list) else str(row.tag_list)
        updated_at = None if pd.isna(row.updated_at) else str(row.updated_at)
        addr_key = matcher.match(row.primary_address1) or row.addr_key
        building_id = building_id_by_addr_key.get(addr_key)
        rows.append(
            (nationbuilder_id, addr_key, building_id, tag_list, updated_at, ingested_at)
        )

    with conn:
        conn.executemany(
            """
            INSERT INTO vtu_membership (
                nationbuilder_id, addr_key, building_id, tag_list, updated_at,
                source_row_ids, ingested_at
            ) VALUES (?, ?, ?, ?, ?, NULL, ?)
            """,
            rows,
        )
    return len(rows)
