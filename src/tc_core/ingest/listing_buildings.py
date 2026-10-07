"""Buildings from landlord listings: the fourth building source, ranked last.

A usable listing (manager_listings.usable_listings) adds a building only
when no building from the City's sources matches it, by the same matching
building names use (normalize.AddressMatcher, so a street-type typo or a
secondary entrance still lands on the City's building), and its address
matches a City address point the same way, which places it. Listings never name an owner: the
building's owner is "(Unknown)" until the registry or a licence says more.
"""

from __future__ import annotations

import json

import polars as pl

from ..normalize import AddressMatcher, sanitize_owner

BUILDING_SOURCE = "manager listing"

# One merged building per row, as merge._deduplicate_buildings() produces
# them; source_row_ids is the JSON stored in buildings.source_row_ids.
BUILDING_SCHEMA = {
    "address": pl.String, "lat": pl.Float64, "lon": pl.Float64, "units": pl.Float64,
    "building_source": pl.String, "year_built": pl.Float64, "n_issues": pl.Float64,
    "issues_details": pl.String, "value_land": pl.Float64, "value_bldg": pl.Float64,
    "bldg_land_ratio": pl.Float64, "owner_group": pl.String, "owner_key": pl.String,
    "local_area": pl.String, "source_row_ids": pl.String, "addr_key": pl.String,
}


def listing_building_rows(
    listings: list[dict],
    known_keys: set[str],
    secondary_index: dict[str, str],
    addr_points: pl.DataFrame,
) -> pl.DataFrame:
    """New building rows, shaped like merge._deduplicate_buildings' output.
    addr_points is merge._prepare_addresses' frame (addr_key, lat, lon,
    geo_local_area). Listings at one address make one building."""
    buildings = AddressMatcher(known_keys, aliases=secondary_index)
    points = {
        row["addr_key"]: row
        for row in addr_points.drop_nulls(["lat", "lon"])
        .unique("addr_key", keep="first", maintain_order=True)
        .iter_rows(named=True)
    }
    address_points = AddressMatcher(list(points))
    found: dict[str, dict] = {}
    for listing in listings:
        address = listing.get("address")
        if not address:
            continue
        if buildings.match(address) is not None:
            continue
        key = address_points.match(address)
        if key is None:
            continue
        rec = found.setdefault(key, {"ids": [], "units": []})
        rec["ids"].append(int(listing["listing_row_id"]))
        if listing.get("units"):
            rec["units"].append(int(listing["units"]))

    rows = []
    for key, rec in found.items():
        point = points[key]
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
            "source_row_ids": json.dumps({"raw_manager_listings": sorted(rec["ids"])}),
            "addr_key": key,
        })
    return pl.DataFrame(rows, schema=BUILDING_SCHEMA)


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
