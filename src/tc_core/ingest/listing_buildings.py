"""Buildings from landlord listings: the fourth building source, ranked last.

A usable listing (manager_listings.usable_listings) adds a building only
when no building from the City's sources matches it, by the same matching
building names use (overlays._match_key, so a street-type typo or a
secondary entrance still lands on the City's building), and its address is
a City address point, which places it. Listings never name an owner: the
building's owner is "(Unknown)" until the registry or a licence says more.
"""

from __future__ import annotations

import pandas as pd

from ..normalize import address_key_variants, sanitize_owner
from .overlays import _build_loose_index, _match_key

BUILDING_SOURCE = "manager listing"

_COLUMNS = [
    "address", "lat", "lon", "units", "building_source", "year_built", "n_issues",
    "issues_details", "value_land", "value_bldg", "bldg_land_ratio", "owner_group",
    "owner_key", "local_area", "source_row_ids", "addr_key",
]


def listing_building_rows(
    listings: list[dict],
    known_keys: set[str],
    secondary_index: dict[str, str],
    addr_points: pd.DataFrame,
) -> pd.DataFrame:
    """New building rows, shaped like merge._deduplicate_buildings' output.
    addr_points is merge._prepare_addresses' frame (addr_key, lat, lon,
    geo_local_area). Listings at one address make one building."""
    loose = _build_loose_index(known_keys)
    points = (
        addr_points.dropna(subset=["lat", "lon"])
        .drop_duplicates("addr_key")
        .set_index("addr_key")
    )
    found: dict[str, dict] = {}
    for listing in listings:
        address = listing.get("address")
        if not address:
            continue
        if _match_key(address, known_keys, secondary_index, loose) in known_keys:
            continue
        key = next((k for k in address_key_variants(address) if k in points.index), None)
        if key is None:
            continue
        rec = found.setdefault(key, {"ids": [], "units": []})
        rec["ids"].append(int(listing["listing_row_id"]))
        if listing.get("units"):
            rec["units"].append(int(listing["units"]))

    rows = []
    for key, rec in found.items():
        point = points.loc[key]
        area = point.get("geo_local_area")
        rows.append({
            "address": key,
            "lat": float(point["lat"]),
            "lon": float(point["lon"]),
            "units": float(max(rec["units"])) if rec["units"] else None,
            "building_source": BUILDING_SOURCE,
            "year_built": None,
            "n_issues": None,
            "issues_details": None,
            "value_land": None,
            "value_bldg": None,
            "bldg_land_ratio": None,
            "owner_group": "(Unknown)",
            "owner_key": sanitize_owner("(Unknown)"),
            "local_area": area.strip() if isinstance(area, str) and area.strip() else "(Unknown)",
            "source_row_ids": {"raw_manager_listings": sorted(rec["ids"])},
            "addr_key": key,
        })
    return pd.DataFrame(rows, columns=_COLUMNS)


def added_from_listings(conn) -> list[tuple[str, str]]:
    """(manager, address) for every building a listing added, for the rebuild
    log: a listing for something that isn't rental housing shows up here."""
    return conn.execute(
        """
        SELECT DISTINCT bl.manager, b.address
        FROM buildings b JOIN building_listings bl ON bl.building_id = b.building_id
        WHERE b.building_source = ?
        ORDER BY bl.manager, b.address
        """,
        (BUILDING_SOURCE,),
    ).fetchall()
