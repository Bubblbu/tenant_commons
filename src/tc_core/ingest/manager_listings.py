"""Accumulate property-manager listing snapshots into raw_manager_listings.

Snapshots are dropped by hand (later: by scrapers) as
data/raw/property_managers/<manager-slug>/<YYYY-MM-DD>.json, each the
manager's own listing feed as fetched that day. The file date is the
snapshot date. Only the listing's id, name, address, URL, status and unit count are stored:
feeds also carry staff contact details, which stay in the raw file.

One feed shape: theliftsystem.com's /v2/search (Tribe Rentals), a list of
{id, name, permalink, address: {address, city}, client: {name}}. Other
managers' scrapers (scripts/fetch_dorset_listings.py) write the same shape.
Listings outside Vancouver stay in the raw file but are skipped: buildings
match on street address alone, so "1234 Fort St" in Victoria would otherwise
attach to a Vancouver building.
Idempotent: re-running over the same snapshots changes nothing, and
first_seen/last_seen only ever widen.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Feed statuses for buildings that don't exist yet: such a listing never adds a
# building, a link or a manager to the map.
UNBUILT_STATUSES = ("in development", "coming soon")


def _listings(path: Path) -> list[dict]:
    rows = []
    for item in json.loads(path.read_text(encoding="utf-8")):
        city = (item.get("address") or {}).get("city")
        if city and city.strip() != "Vancouver":
            continue
        address = (item.get("address") or {}).get("address")
        units = item.get("units")
        rows.append({
            "manager": (item.get("client") or {}).get("name") or path.parent.name,
            "external_id": str(item["id"]),
            "name": (item.get("name") or "").strip() or None,
            "address": (address or "").strip() or None,
            "url": item.get("permalink") or None,
            "status": (item.get("status") or "").strip() or None,
            "units": int(units) if isinstance(units, (int, float)) and units > 0 else None,
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
                        (manager, external_id, name, address, url, status, units, first_seen, last_seen)
                    VALUES (:manager, :external_id, :name, :address, :url, :status, :units, :seen, :seen)
                    ON CONFLICT (manager, external_id) DO UPDATE SET
                        name = CASE WHEN :seen >= last_seen THEN excluded.name ELSE name END,
                        address = CASE WHEN :seen >= last_seen THEN excluded.address ELSE address END,
                        url = CASE WHEN :seen >= last_seen THEN excluded.url ELSE url END,
                        status = CASE WHEN :seen >= last_seen THEN excluded.status ELSE status END,
                        units = CASE WHEN :seen >= last_seen THEN excluded.units ELSE units END,
                        first_seen = min(first_seen, :seen),
                        last_seen = max(last_seen, :seen)
                    """,
                    {**row, "seen": seen},
                )
                n += 1
    return n


def usable_listings(conn: sqlite3.Connection) -> list[dict]:
    """Listings that may add a building, a link or a manager to the map: in
    their manager's latest snapshot (a listing that dropped out stays in the
    table as history) and not for an unbuilt building."""
    marks = ", ".join("?" for _ in UNBUILT_STATUSES)
    rows = conn.execute(
        f"""
        SELECT l.listing_row_id, l.manager, l.name, l.address, l.url, l.last_seen, l.units
        FROM raw_manager_listings l
        JOIN (SELECT manager, max(last_seen) AS latest FROM raw_manager_listings GROUP BY manager) m
          ON m.manager = l.manager AND m.latest = l.last_seen
        WHERE lower(trim(coalesce(l.status, ''))) NOT IN ({marks})
        ORDER BY l.listing_row_id
        """,
        UNBUILT_STATUSES,
    ).fetchall()
    keys = ("listing_row_id", "manager", "name", "address", "url", "last_seen", "units")
    return [dict(zip(keys, r)) for r in rows]
