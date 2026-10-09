"""Merge raw_buildings + raw_addresses into buildings + landlords.

Ports the address-matching/dedup logic from the retired `src/sica_mapping/data/spatial.py`
(select_west_end_buildings + join_buildings_addresses + deduplicate_buildings)
against data already sitting in SQLite, with two deliberate deviations from v1:

1. `_parse_money()` replaces a bare numeric cast (v1: `pd.to_numeric(errors="coerce")`) for
   value_land/value_bldg. The source mixes plain numbers with
   "$35,407,000.00"-style strings — 100% of West End rows use the latter
   format, and the naive cast silently nulls all of them in v1 today.
2. No `allowed_areas` filter, ever. `local_area` is kept as a plain column;
   scope-narrowing is deferred to query/export time, matching the fact that
   buildings.csv is already city-wide, not West-End-scoped.

Also assigns `block_id` (point-in-polygon against `blocks`, forked from
`point_in_block_ids`'s STRtree logic) and upserts `landlords` — neither of
which have a home anywhere else in the ingest sequence.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone

import numpy as np
import polars as pl
from shapely.geometry import Point
from shapely.strtree import STRtree

from ..db import query_frame
from ..geometry import parse_geom
from ..normalize import (
    addr_key_from_freeform,
    clean_owner_label,
    normalize_street,
    parse_lat_lon,
    sanitize_owner,
)
from .listing_buildings import BUILDING_SCHEMA, listing_building_rows
from .listing_buildings import BUILDING_SOURCE as LISTING_SOURCE
from .manager_listings import usable_listings
from .overlay_sources import load_secondary_address_index

OWNER_CANDIDATES = [
    "bsns_group",
    "business_group",
    "owner_group",
    "owner",
    "ownership_group",
]


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _parse_money(raw: object) -> float | None:
    """'$35,407,000.00' / '5343000' / '' / None -> float or None."""
    if _missing(raw):
        return None
    s = str(raw).strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _numeric(col: str) -> pl.Expr:
    """The column as floats; text that isn't a number becomes null."""
    return pl.col(col).cast(pl.String).cast(pl.Float64, strict=False)


def _text(col: str) -> pl.Expr:
    return pl.col(col).cast(pl.String)


def load_raw_frames(conn: sqlite3.Connection) -> tuple[pl.DataFrame, pl.DataFrame]:
    raw_buildings = query_frame(conn, "SELECT * FROM raw_buildings")
    raw_addresses = query_frame(conn, "SELECT * FROM raw_addresses")
    return raw_buildings, raw_addresses


def _address_point_key(street, civic) -> str:
    if _missing(street):
        return addr_key_from_freeform("")
    if _missing(civic):
        return addr_key_from_freeform(str(street))
    if float(civic).is_integer():
        civic_str = str(int(civic))
    else:
        civic_str = str(civic).rstrip("0").rstrip(".")
    return addr_key_from_freeform(f"{civic_str} {street}")


def _prepare_addresses(addr_df: pl.DataFrame) -> pl.DataFrame:
    # parse_lat_lon() gives NaN for an unparseable point: missing, here.
    coords = [parse_lat_lon(s) for s in addr_df["geo_point_2d"].to_list()]
    addr_df = addr_df.with_columns(
        lat=pl.Series([c[0] for c in coords], dtype=pl.Float64).fill_nan(None),
        lon=pl.Series([c[1] for c in coords], dtype=pl.Float64).fill_nan(None),
        street_norm=_text("std_street").map_elements(normalize_street, return_dtype=pl.String),
        civic_number_int=_numeric("civic_number"),
    )
    return addr_df.with_columns(
        addr_key=pl.Series(
            [
                _address_point_key(street, civic)
                for street, civic in zip(addr_df["std_street"], addr_df["civic_number_int"])
            ],
            dtype=pl.String,
        )
    )


def _select_buildings(bldg_df: pl.DataFrame) -> tuple[pl.DataFrame, str]:
    key = lambda col: _text(col).map_elements(
        addr_key_from_freeform, return_dtype=pl.String, skip_nulls=False
    )
    df = bldg_df.with_columns(
        local_area=_text("local_area").fill_null("(Unknown)"),
        addr_key=key("address"),
    )
    if "primary_address" in df.columns:
        df = df.with_columns(addr_key_primary=key("primary_address").fill_null(pl.col("addr_key")))
    else:
        df = df.with_columns(addr_key_primary=pl.col("addr_key"))

    owner_col = next((c for c in OWNER_CANDIDATES if c in df.columns), None)
    if owner_col is None:
        owner_col = next(
            (c for c in df.columns if ("group" in c or "owner" in c)), None
        )
    if owner_col is None:
        owner_col = "bsns_group"
        df = df.with_columns(pl.lit("(Unknown)").alias(owner_col))
    return df, owner_col


def _clean_area(col: str) -> pl.Expr:
    s = _text(col).str.strip_chars()
    return pl.when(s == "").then(None).otherwise(s)


def _nearest_address_point(
    addr_text: str, street_lookup: dict[str, list[dict]]
) -> dict | None:
    """For a building with no exact address-point match: the point on the same
    street with the nearest civic number (else the street's first point)."""
    parts = addr_key_from_freeform(addr_text).split(" ", 1)
    if len(parts) < 2:
        return None
    try:
        civic_val = float(parts[0])
    except ValueError:
        civic_val = None
    candidates = street_lookup.get(parts[1])
    if not candidates:
        return None
    if civic_val is not None:
        numeric = [c for c in candidates if c["civic_number_int"] is not None]
        if numeric:
            return min(numeric, key=lambda c: abs(c["civic_number_int"] - civic_val))
    return candidates[0]


def _join_buildings_addresses(west: pl.DataFrame, addr_df: pl.DataFrame) -> pl.DataFrame:
    area_cols = [col for col in addr_df.columns if "local_area" in col]
    addr_cols = ["addr_key", "lat", "lon", "street_norm", "civic_number_int"] + [
        col for col in area_cols if col not in {"lat", "lon"}
    ]
    addr_lookup = addr_df.select(addr_cols).unique("addr_key", keep="first", maintain_order=True)

    joined = west.join(addr_lookup, on="addr_key", how="left", maintain_order="left")
    rename_map = {"addr_key": "addr_key_primary", "lat": "lat_primary", "lon": "lon_primary"}
    for col in area_cols:
        rename_map[col] = f"{col}_primary"
    alt_lookup = addr_lookup.select(list(rename_map)).rename(rename_map)
    joined = joined.join(alt_lookup, on="addr_key_primary", how="left", maintain_order="left")
    joined = joined.with_columns(
        lat=pl.col("lat").fill_null(pl.col("lat_primary")),
        lon=pl.col("lon").fill_null(pl.col("lon_primary")),
        *(pl.col(col).fill_null(pl.col(f"{col}_primary")).alias(col) for col in area_cols),
    ).drop("lat_primary", "lon_primary", *(f"{col}_primary" for col in area_cols))

    if "local_area" not in joined.columns:
        joined = joined.with_columns(local_area=pl.lit("(Unknown)"))
    area_candidates = [
        col for col in area_cols if col in joined.columns and col != "local_area"
    ]
    if area_candidates:
        own = _clean_area("local_area")
        unknown = own.is_null() | (own == "(Unknown)")
        joined = joined.with_columns(
            local_area=pl.when(unknown)
            .then(pl.coalesce([_clean_area(col) for col in area_candidates]))
            .otherwise(own)
            .fill_null("(Unknown)")
        )

    missing = joined.select(pl.col("lat").is_null() | pl.col("lon").is_null()).to_series()
    if missing.any():
        street_lookup: dict[str, list[dict]] = {}
        for point in addr_df.drop_nulls(["lat", "lon"]).iter_rows(named=True):
            if point["street_norm"] is not None:
                street_lookup.setdefault(point["street_norm"], []).append(point)

        lats, lons, areas = (joined[c].to_list() for c in ("lat", "lon", "local_area"))
        for i in missing.arg_true().to_list():
            choice = _nearest_address_point(joined["address"][i], street_lookup)
            if choice is None:
                continue
            lats[i], lons[i] = choice["lat"], choice["lon"]
            if areas[i] in {None, "", "(Unknown)"}:
                candidate_area = next(
                    (str(choice[col]).strip() for col in area_candidates if choice.get(col) is not None),
                    None,
                )
                if candidate_area:
                    areas[i] = candidate_area
        joined = joined.with_columns(
            lat=pl.Series(lats, dtype=pl.Float64),
            lon=pl.Series(lons, dtype=pl.Float64),
            local_area=pl.Series(areas, dtype=pl.String),
        )

    joined = joined.drop(*area_candidates, "street_norm", "civic_number_int", strict=False)
    return joined.with_columns(
        *(_numeric(col).alias(col) for col in ("units", "year_built", "n_issues", "bldg_land_ratio")),
        *(
            pl.col(col).map_elements(_parse_money, return_dtype=pl.Float64, skip_nulls=False)
            for col in ("value_land", "value_bldg")
        ),
    )


# Landlord listings come last: they add buildings no City source lists, and never win a merge.
BUILDING_SOURCE_ORDER = ("rental inventory", "non-market housing list", "rental licence", LISTING_SOURCE)


def _most_common(col: str) -> pl.Expr:
    """The most frequent non-null value; ties go to the smallest (pandas'
    mode().iloc[0])."""
    return pl.col(col).drop_nulls().mode().min()


def _deduplicate_buildings(df: pl.DataFrame, owner_col: str) -> pl.DataFrame:
    """One building per addr_key, in order of first appearance."""
    rank = {source: i for i, source in enumerate(BUILDING_SOURCE_ORDER)}
    df = df.with_columns(
        _owner=_text(owner_col).map_elements(clean_owner_label, return_dtype=pl.String),
        _source_rank=_text("building_source").replace_strict(rank, default=None, return_dtype=pl.Int64),
    )
    out = df.group_by("addr_key", maintain_order=True).agg(
        address=pl.coalesce(_most_common("address"), pl.col("address").first()),
        lat=pl.col("lat").drop_nulls().first(),
        lon=pl.col("lon").drop_nulls().first(),
        units=pl.col("units").max(),
        # A City list beats a licence: "rental licence" only when no source row is listed.
        _source_rank=pl.col("_source_rank").min(),
        year_built=pl.col("year_built").median(),
        n_issues=pl.col("n_issues").max(),
        # The City's rental-standards detail page for whichever row
        # contributed the max n_issues (matches it, rather than an arbitrary
        # row's URL, on the rare chance a building has more than one).
        issues_details=pl.col("issues_details").get(pl.col("n_issues").arg_max()),
        value_land=pl.col("value_land").median(),
        value_bldg=pl.col("value_bldg").median(),
        _ratio=pl.col("bldg_land_ratio").median(),
        _owner=pl.coalesce(_most_common("_owner"), pl.col("_owner").drop_nulls().first()),
        local_area=pl.coalesce(_most_common("local_area"), pl.lit("(Unknown)")),
        source_row_ids=pl.col("raw_building_id").drop_nulls().unique().sort(),
    )
    owners = [clean_owner_label(o if o is not None else "(Unknown)") for o in out["_owner"]]
    return (
        out.with_columns(
            building_source=pl.col("_source_rank").replace_strict(
                dict(enumerate(BUILDING_SOURCE_ORDER)), default=None, return_dtype=pl.String
            ),
            bldg_land_ratio=pl.coalesce(
                "_ratio",
                pl.when(pl.col("value_land") != 0).then(pl.col("value_bldg") / pl.col("value_land")),
            ),
            owner_group=pl.Series(owners, dtype=pl.String),
            owner_key=pl.Series([sanitize_owner(o) for o in owners], dtype=pl.String),
            source_row_ids=pl.Series(
                [json.dumps(ids) for ids in out["source_row_ids"].to_list()], dtype=pl.String
            ),
        )
        .select([pl.col(c).cast(t) for c, t in BUILDING_SCHEMA.items()])
        .drop_nulls(["lat", "lon"])
    )


def merge_and_dedupe_buildings(
    raw_buildings: pl.DataFrame,
    raw_addresses: pl.DataFrame,
    listings: list[dict] | None = None,
    secondary_index: dict[str, str] | None = None,
) -> pl.DataFrame:
    addr_df = _prepare_addresses(raw_addresses)
    west, owner_col = _select_buildings(raw_buildings)
    joined = _join_buildings_addresses(west, addr_df)
    buildings = _deduplicate_buildings(joined, owner_col)
    if listings:
        known = set(buildings["addr_key"].to_list())
        extra = listing_building_rows(listings, known, secondary_index or {}, addr_df)
        if not extra.is_empty():
            buildings = pl.concat([buildings, extra])
    return buildings


def assign_blocks(buildings_df: pl.DataFrame, blocks_df: pl.DataFrame) -> list[int | None]:
    """Fork of point_in_block_ids (STRtree). block_id per row, None if unmatched."""
    geoms = []
    block_ids = []
    for raw_geom, block_id in zip(blocks_df["geom"], blocks_df["block_id"]):
        geom = parse_geom(raw_geom)
        if geom is None:
            continue
        geoms.append(geom)
        block_ids.append(int(block_id))

    if not geoms:
        return [None] * buildings_df.height

    tree = STRtree(geoms)

    def locate(lon: float, lat: float) -> int | None:
        if _missing(lat) or _missing(lon):
            return None
        point = Point(lon, lat)
        for idx in np.atleast_1d(tree.query(point)):
            geom = geoms[int(idx)]
            if geom.contains(point) or geom.touches(point):
                return block_ids[int(idx)]
        return None

    return [locate(lo, la) for la, lo in zip(buildings_df["lat"], buildings_df["lon"])]


def upsert_landlords(conn: sqlite3.Connection, buildings_df: pl.DataFrame) -> dict[str, int]:
    """One row per distinct owner_key, excluding 'unknown'. Returns owner_key -> landlord_id."""
    now = datetime.now(timezone.utc).isoformat()
    distinct = (
        buildings_df.filter(pl.col("owner_key") != "unknown")
        .select("owner_key", "owner_group")
        .unique("owner_key", keep="first", maintain_order=True)
    )
    owner_key_to_id: dict[str, int] = {}
    with conn:
        for owner_key, owner_group in distinct.iter_rows():
            cur = conn.execute(
                "INSERT INTO landlords (display_name, owner_key, source_row_ids, created_at, updated_at) "
                "VALUES (?, ?, NULL, ?, ?)",
                (owner_group, owner_key, now, now),
            )
            owner_key_to_id[owner_key] = cur.lastrowid
    return owner_key_to_id


def write_buildings(
    conn: sqlite3.Connection,
    buildings_df: pl.DataFrame,
    landlord_id_by_owner_key: dict[str, int],
    block_ids: list[int | None],
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for row, block_id in zip(buildings_df.iter_rows(named=True), block_ids):
        rows.append(
            (
                row["addr_key"],
                row["address"],
                row["local_area"],
                row["lat"],
                row["lon"],
                row["units"],
                row["building_source"],
                row["year_built"],
                row["value_land"],
                row["value_bldg"],
                row["bldg_land_ratio"],
                row["n_issues"],
                row["issues_details"],
                landlord_id_by_owner_key.get(row["owner_key"]),
                block_id,
                row["source_row_ids"],
                now,
                now,
            )
        )
    with conn:
        conn.executemany(
            """
            INSERT INTO buildings (
                addr_key, address, local_area, lat, lon, units, building_source, year_built,
                value_land, value_bldg, bldg_land_ratio, n_issues, issues_details,
                landlord_id, block_id, source_row_ids, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def run_merge(conn: sqlite3.Connection) -> int:
    raw_buildings, raw_addresses = load_raw_frames(conn)
    listings = usable_listings(conn)
    secondary = load_secondary_address_index(conn) if listings else {}
    buildings_df = merge_and_dedupe_buildings(raw_buildings, raw_addresses, listings, secondary)

    blocks_df = query_frame(conn, "SELECT block_id, geom FROM blocks")
    block_ids = assign_blocks(buildings_df, blocks_df)

    landlord_id_by_owner_key = upsert_landlords(conn, buildings_df)
    return write_buildings(conn, buildings_df, landlord_id_by_owner_key, block_ids)
