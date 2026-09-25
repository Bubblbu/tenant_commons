"""Accumulate property-manager listing snapshots into raw_manager_listings.

Snapshots are dropped by hand (later: by scrapers) as
data/raw/property_managers/<manager-slug>/<YYYY-MM-DD>.json, each the
manager's own listing feed as fetched that day. The file date is the
snapshot date. Only the listing's id, name, address and URL are stored:
feeds also carry staff contact details, which stay in the raw file.

Currently one feed shape, theliftsystem.com's /v2/search (Tribe Rentals):
a list of {id, name, permalink, address: {address}, client: {name}}.
Idempotent: re-running over the same snapshots changes nothing, and
first_seen/last_seen only ever widen.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _listings(path: Path) -> list[dict]:
    rows = []
    for item in json.loads(path.read_text(encoding="utf-8")):
        address = (item.get("address") or {}).get("address")
        rows.append({
            "manager": (item.get("client") or {}).get("name") or path.parent.name,
            "external_id": str(item["id"]),
            "name": (item.get("name") or "").strip() or None,
            "address": (address or "").strip() or None,
            "url": item.get("permalink") or None,
        })
    return rows


def ingest_manager_listings(conn: sqlite3.Connection, listings_dir: str) -> int:
    """Upsert every snapshot under listings_dir; returns listings seen."""
    snapshots = sorted(
        p for p in Path(listings_dir).glob("*/*.json") if _DATE_RE.match(p.stem)
    )
    n = 0
    with conn:
        for path in snapshots:
            seen = path.stem
            for row in _listings(path):
                conn.execute(
                    """
                    INSERT INTO raw_manager_listings
                        (manager, external_id, name, address, url, first_seen, last_seen)
                    VALUES (:manager, :external_id, :name, :address, :url, :seen, :seen)
                    ON CONFLICT (manager, external_id) DO UPDATE SET
                        name = CASE WHEN :seen >= last_seen THEN excluded.name ELSE name END,
                        address = CASE WHEN :seen >= last_seen THEN excluded.address ELSE address END,
                        url = CASE WHEN :seen >= last_seen THEN excluded.url ELSE url END,
                        first_seen = min(first_seen, :seen),
                        last_seen = max(last_seen, :seen)
                    """,
                    {**row, "seen": seen},
                )
                n += 1
    return n
