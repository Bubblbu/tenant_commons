"""Collect every name a source gives a building into building_names.

Sources: the FOI rental list's building name and the non-market housing
list's project name (raw_buildings.foi_name / .name), rental-licence trade
names (raw_buildings.bsns_trade_name, ";"-joined), SRO/co-op names attached
by the overlay matcher (buildings.housing_name), and property-manager
listings (raw_manager_listings), matched to buildings the same way co-op
and SRO addresses are. The map shows one name, `pick_building_name()`.
"""

from __future__ import annotations

import json
import re
import sqlite3

from .overlay_sources import load_secondary_address_index
from .overlays import _build_loose_index, _match_key

# Operating names first: the name a building runs under (licence, the
# manager's own listing) before the names on City lists.
NAME_SOURCE_ORDER = [
    "licence_trade_name",
    "manager_listing",
    "foi_rental_list",
    "non_market_list",
    "sro_list",
    "coop_list",
]


def _name_key(name: str) -> str:
    """Spellings of one name compare equal ("Stamp's Place" ~ "STAMPS PLACE")."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def pick_building_name(names: list[tuple[str, str]]) -> tuple[str | None, list[str]]:
    """(display name, other distinct names) from (name, source_type) pairs."""
    rank = {s: i for i, s in enumerate(NAME_SOURCE_ORDER)}
    ordered = sorted(names, key=lambda n: rank.get(n[1], len(rank)))
    picked: list[str] = []
    seen: set[str] = set()
    for name, _ in ordered:
        key = _name_key(name)
        if key and key not in seen:
            seen.add(key)
            picked.append(name)
    return (picked[0], picked[1:]) if picked else (None, [])


def derive_building_names(conn: sqlite3.Connection) -> int:
    buildings = conn.execute(
        "SELECT building_id, addr_key, source_row_ids, housing_name, is_sro, is_coop FROM buildings"
    ).fetchall()
    raw = {
        row[0]: row[1:]
        for row in conn.execute(
            "SELECT raw_building_id, foi_name, name, bsns_trade_name FROM raw_buildings"
        )
    }
    rows: list[tuple] = []

    def add(bid, name, source_type, table=None, row_id=None):
        name = (name or "").strip()
        if name:
            rows.append((bid, name, source_type, table, row_id))

    by_key = {}
    for bid, addr_key, source_ids, housing_name, is_sro, is_coop in buildings:
        by_key[addr_key] = bid
        for raw_id in json.loads(source_ids or "[]"):
            foi_name, nm_name, trade = raw.get(raw_id, (None, None, None))
            add(bid, foi_name, "foi_rental_list", "raw_buildings", raw_id)
            add(bid, nm_name, "non_market_list", "raw_buildings", raw_id)
            for part in (trade or "").split(";"):
                add(bid, part, "licence_trade_name", "raw_buildings", raw_id)
        if housing_name:
            add(bid, housing_name, "coop_list" if is_coop else "sro_list")

    known = set(by_key)
    secondary = load_secondary_address_index(conn)
    loose = _build_loose_index(known)
    for row_id, name, address in conn.execute(
        "SELECT listing_row_id, name, address FROM raw_manager_listings"
    ):
        if not address:
            continue
        key = _match_key(address, known, secondary, loose)
        if key in by_key:
            add(by_key[key], name, "manager_listing", "raw_manager_listings", row_id)

    with conn:
        conn.execute("DELETE FROM building_names")
        conn.executemany(
            "INSERT INTO building_names (building_id, name, source_type, source_table, source_row_id) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)
