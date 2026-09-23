"""Match SRO/SRA, co-op, and rezoning-application datasets against buildings.

Runs at ingest time against SQLite (ported from the retired
`sica_mapping/data/overlays.py`, which read these sources from CSV at render
time). `buildings_df` must already
carry `addr_key`, `lat`/`lon`. For each optional source table, splits rows
into "matched" (joins onto an existing building by address) and "unmatched".
Unmatched co-op and SRO/SRA records are housing too, so they are returned
separately as candidate `overlay_housing` rows. Unmatched rezoning records
stay in the body's own `unmatched_records` list; rezoning isn't shown on the
map for now, but its matching is kept as-is.

Matching is address-key only (`tc_core.normalize.addr_key_from_freeform`), no
lat/lon proximity fallback — a deliberate precision-over-recall choice. Each
source needs different preprocessing before it produces a clean key:

- Co-ops: `address` is "123 Foo St, Vancouver, BC V1V 1V1" — strip everything
  from the first comma before keying.
- SRO/SRA: `address` is already a clean single-line address ("210 Abbott
  St.") — key directly. Note the CSV's own `match_method` column (an
  upstream address-matching flag baked into the source data) is unrelated to
  our own matching here and is intentionally not used to filter rows.
- Rezoning: `name` is free text, not an address ("2165-2195 and 2205-2291 W
  45th Av (Dunbar Ryerson United Church)") — strip from the first "(", split
  the remainder on " and "/"&"/";", and key the first fragment. Best-effort:
  most rezoning applications (churches, single-family lots, commercial,
  multi-lot assemblies) don't correspond to any row in `buildings` at all,
  regardless of parsing quality.

Co-ops and SRO/SRA additionally get a secondary-address fallback: since the
vhd pipeline's 2026-08-07 refresh, `raw_buildings` carries a
`secondary_addresses` column (other civic addresses VanMaps resolves to the
same building — e.g. a podium building with several street-facing unit
entrances). A source record whose address doesn't key-match any building's
own `address` may still key-match one of those secondary addresses; see
`load_secondary_address_index` in `.overlay_sources`. Not applied to
rezoning, which doesn't key off a civic address in the first place.

Measured match rates against buildings (5,112 rows, citywide, pre-
secondary-address fallback): co-ops 42/117 (36%), SRO/SRA 41/171 (24%),
rezoning ~43/377 (11%).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape

from ..normalize import addr_key_from_freeform
from .overlay_sources import (
    load_boundary_feature_collection,
    load_coops_frame,
    load_rezoning_frame,
    load_secondary_address_index,
    load_sro_frame,
)

logger = logging.getLogger("tc_core.ingest.overlays")


def rezoning_status_group(status: str) -> str:
    """"closed" once approved, "open" for anything still in progress (Rezoning/Upcoming)."""
    return "closed" if str(status).strip().lower() == "approved" else "open"


@dataclass
class OverlayMatchResult:
    matched: pd.DataFrame
    unmatched: list[dict] = field(default_factory=list)


def _clean(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _build_boundary_polys(local_area_boundary_fc: dict) -> list[tuple[str, object]]:
    polys = []
    for feat in (local_area_boundary_fc or {}).get("features") or []:
        props = feat.get("properties") or {}
        name = str(props.get("name") or "").strip()
        geom = feat.get("geometry")
        if not geom or not name:
            continue
        try:
            polys.append((name, shape(geom)))
        except Exception:
            continue
    return polys


def _resolve_local_area(lat, lon, boundary_polys: list[tuple[str, object]]) -> str:
    """Point-in-polygon lookup against the 22 official local-area boundaries.

    Deliberately not trusting each source's own free-text area field (e.g.
    SRO's "Area" is a DTES-style composite label, not one of the 22 official
    local areas the sidebar's neighbourhood checkboxes are built from) — an
    unmatched marker needs a local_area that actually lines up with those
    checkboxes to be filterable correctly.
    """
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return ""
    point = Point(float(lon), float(lat))
    for name, poly in boundary_polys:
        if poly.contains(point):
            return name
    return ""


_DIRECTION_RE = re.compile(r"^(\d+)\s+(east|west|north|south)\b")
_DIRECTION_ABBR = {"east": "e", "west": "w", "north": "n", "south": "s"}
# "#800 - 1047 Barclay St", "100-2950 Heather St": a unit number in front of
# the civic number. (Not a range like "2165-2195 W 45th Av" — see
# `_match_key`, which only falls back to this when the full address misses.)
_UNIT_PREFIX_RE = re.compile(r"^#?\s*\w+\s*-\s*(\d+\s.+)$")
# "7401 - 7469 Talon Square", "500 & 502 Alexander St": a range of civic
# numbers; the building is keyed by the first.
_RANGE_RE = re.compile(r"^(\d+)\s*(?:-|&|and)\s*\d+\s+(.+)$")
_STREET_TYPE_RE = re.compile(r"^(\d+ .+?)(?: (?:st|ave|rd|dr|blvd|pl|ct|hwy))?$")


def _loose_key(key: str) -> str:
    """addr_key without its street type ("404 hawks av" ~ "404 hawks st")."""
    m = _STREET_TYPE_RE.match(key)
    return m.group(1) if m else key


def _build_loose_index(known_keys: set[str]) -> dict[str, str]:
    """loose key -> building key, only where exactly one building has it."""
    seen: dict[str, set[str]] = {}
    for key in known_keys:
        seen.setdefault(_loose_key(key), set()).add(key)
    return {loose: next(iter(keys)) for loose, keys in seen.items() if len(keys) == 1}


def _address_key_variants(street: str) -> list[str]:
    """Candidate addr_keys for a source address, most literal first.

    buildings.csv keys use "e"/"w" for directions ("1865 e 10th ave") where
    co-op sources spell them out ("1865 East 10th Avenue"), and co-op units
    are often listed with their unit number in front. Neither is handled by
    the shared `addr_key_from_freeform` (its output is baked into the cached
    building keys, so it can't change), so the variants are built here.
    """
    base = re.sub(r"\s+", " ", str(street)).strip().lower().rstrip("*").strip()
    raw = [base]
    m = _UNIT_PREFIX_RE.match(base)
    if m:
        raw.append(m.group(1))
    m = _RANGE_RE.match(base)
    if m:
        raw.append(f"{m.group(1)} {m.group(2)}")
    keys: list[str] = []
    for text in raw:
        text = _DIRECTION_RE.sub(lambda d: f"{d.group(1)} {_DIRECTION_ABBR[d.group(2)]}", text)
        key = addr_key_from_freeform(text)
        if key not in keys:
            keys.append(key)
    return keys


def _match_key(
    street: str,
    known_keys: set[str],
    secondary_index: dict[str, str],
    loose_index: dict[str, str],
) -> str:
    """The first variant that hits a building (directly, or via a secondary
    address), then the first that hits one ignoring street type ("St" vs
    "Av" typos, only when that number+street is unambiguous); otherwise the
    most-stripped variant, so unmatched records for different units of one
    building end up sharing a key (and one marker).
    """
    variants = _address_key_variants(street)
    for key in variants:
        if key in known_keys:
            return key
        if key in secondary_index:
            return secondary_index[key]
    for key in variants:
        if _loose_key(key) in loose_index:
            return loose_index[_loose_key(key)]
    return variants[-1]


def _coop_street(address) -> str:
    return str(address).split(",")[0].strip()


_REZONING_NAME_SPLIT_RE = re.compile(r"\s+and\s+|\s*&\s*|;")


def _rezoning_addr_key(name) -> str:
    s = str(name).split("(")[0]
    s = _REZONING_NAME_SPLIT_RE.split(s, maxsplit=1)[0].strip()
    return addr_key_from_freeform(s)


def _add_extra_housing(
    extras: dict[str, dict],
    key: str,
    lat,
    lon,
    address: str,
    flags: dict,
    name: str,
    source_table: str,
    source_id,
) -> None:
    """Queue a source record with no building match as a new housing row.

    Keyed by address so a co-op and an SRO at the same unmatched address
    become one building with both flags, like a matched dual-type building.
    Records without coordinates can't be placed on the map and are skipped.
    `source_row_ids` (CLAUDE.md lineage hook) keeps every contributing raw
    row per table, since one row can merge a co-op and an SRO.
    """
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        logger.warning("Skipping unplaceable housing record (no lat/lon): %s", address)
        return
    row = extras.setdefault(
        key, {"addr_key": key, "address": address, "lat": float(lat), "lon": float(lon)}
    )
    row.update(flags)
    if source_id is not None and not pd.isna(source_id):
        row.setdefault("source_row_ids", {}).setdefault(source_table, []).append(
            int(source_id)
        )
    if name and not row.get("housing_name"):
        row["housing_name"] = name


def match_overlays(
    conn: sqlite3.Connection,
    buildings_df: pd.DataFrame,
    boundary_path: str,
) -> OverlayMatchResult:
    df = buildings_df.copy()
    addr_keys = set(df["addr_key"])
    boundary_polys = _build_boundary_polys(load_boundary_feature_collection(boundary_path))
    secondary_index = load_secondary_address_index(conn)
    loose_index = _build_loose_index(addr_keys)
    coops = load_coops_frame(conn)
    sro = load_sro_frame(conn)
    rezoning = load_rezoning_frame(conn)
    if secondary_index:
        logger.info(
            "Secondary-address fallback: %d secondary addresses "
            "available for co-op/SRO matching",
            len(secondary_index),
        )
    unmatched_records: list[dict] = []
    # SRO/co-op source records with no matching building, keyed by addr_key.
    # Returned as `unmatched`; ingest writes them to `overlay_housing`, a
    # companion table, not to `buildings` (see overlay_write.py).
    extras: dict[str, dict] = {}

    # Defaults for every new column, so downstream code never needs to branch
    # on a column being absent. overlay_write.BUILDING_OVERLAY_COLUMNS lists
    # these same 18 (a test pins the two together).
    df["is_coop"] = False
    df["coop_status"] = ""
    df["coop_ownership_model"] = ""
    df["coop_url"] = ""
    df["housing_name"] = ""
    df["is_sro"] = False
    df["sro_owner"] = ""
    df["sro_operator"] = ""
    df["sro_operator_group"] = ""
    df["sro_ownership_group"] = ""
    df["sro_occupancy_status"] = ""
    df["sro_registered_rooms"] = ""
    df["is_rezoning"] = False
    df["rezoning_status"] = ""
    df["rezoning_status_group"] = ""
    df["rezoning_category"] = ""
    df["rezoning_status_detail"] = ""
    df["rezoning_link"] = ""

    # ---- Co-ops ----
    if coops is not None:
        coops = coops.copy()
        coops["addr_key"] = coops["address"].apply(
            lambda a: _match_key(_coop_street(a), addr_keys, secondary_index, loose_index)
        )
        matched_mask = coops["addr_key"].isin(addr_keys)
        matched = coops[matched_mask].drop_duplicates("addr_key")
        unmatched = coops[~matched_mask]
        logger.info(
            "Co-ops: %d/%d matched an existing building", len(matched), len(coops)
        )

        if not matched.empty:
            lookup = matched.set_index("addr_key")
            hit = df["addr_key"].isin(lookup.index)
            df.loc[hit, "is_coop"] = True
            df.loc[hit, "coop_status"] = (
                df.loc[hit, "addr_key"].map(lookup["status"]).apply(_clean)
            )
            df.loc[hit, "coop_ownership_model"] = (
                df.loc[hit, "addr_key"].map(lookup["ownership_model"]).apply(_clean)
            )
            df.loc[hit, "coop_url"] = (
                df.loc[hit, "addr_key"].map(lookup["read_more_url"]).apply(_clean)
            )
            df.loc[hit, "housing_name"] = (
                df.loc[hit, "addr_key"].map(lookup["title"]).apply(_clean)
            )

        for _, row in unmatched.iterrows():
            _add_extra_housing(
                extras,
                key=row["addr_key"],
                lat=row.get("lat"),
                lon=row.get("lon"),
                address=_clean(row.get("address")).split(",")[0].strip(),
                flags={
                    "is_coop": True,
                    "coop_status": _clean(row.get("status")),
                    "coop_ownership_model": _clean(row.get("ownership_model")),
                    "coop_url": _clean(row.get("read_more_url")),
                },
                name=_clean(row.get("title")),
                source_table="raw_coops",
                source_id=row.get("raw_coop_id"),
            )

    # ---- SRO/SRA housing ----
    if sro is not None:
        sro = sro.copy()
        sro["addr_key"] = sro["address"].apply(
            lambda a: _match_key(str(a), addr_keys, secondary_index, loose_index)
        )
        matched_mask = sro["addr_key"].isin(addr_keys)
        matched = sro[matched_mask].drop_duplicates("addr_key")
        unmatched = sro[~matched_mask]
        logger.info(
            "SRO/SRA: %d/%d matched an existing building", len(matched), len(sro)
        )

        if not matched.empty:
            lookup = matched.set_index("addr_key")
            hit = df["addr_key"].isin(lookup.index)
            df.loc[hit, "is_sro"] = True
            field_map = {
                "owner": "sro_owner",
                "operator": "sro_operator",
                "operator_group": "sro_operator_group",
                "ownership_group": "sro_ownership_group",
                "occupancy_status": "sro_occupancy_status",
                "#_registered_rooms": "sro_registered_rooms",
            }
            for src_col, dst_col in field_map.items():
                if src_col in lookup.columns:
                    df.loc[hit, dst_col] = (
                        df.loc[hit, "addr_key"].map(lookup[src_col]).apply(_clean)
                    )

            # Units fill-in (a room still houses a tenant): only where the
            # building has no real unit count already (e.g. no FOI/rental
            # inventory match) — never overwrite a reported number. Requires
            # the caller's buildings_df to have carried a `units` column;
            # ingest_overlays() does, the matcher-columns pinning test does
            # not, so this is a no-op there rather than a KeyError.
            if "units" in df.columns:
                rooms_numeric = pd.to_numeric(df["sro_registered_rooms"], errors="coerce")
                fill_mask = df["is_sro"] & df["units"].isna() & rooms_numeric.notna()
                df.loc[fill_mask, "units"] = rooms_numeric[fill_mask]

        for _, row in unmatched.iterrows():
            _add_extra_housing(
                extras,
                key=row["addr_key"],
                lat=row.get("latitude"),
                lon=row.get("longitude"),
                address=_clean(row.get("address")),
                flags={
                    "is_sro": True,
                    "sro_owner": _clean(row.get("owner")),
                    "sro_operator": _clean(row.get("operator")),
                    "sro_operator_group": _clean(row.get("operator_group")),
                    "sro_ownership_group": _clean(row.get("ownership_group")),
                    "sro_occupancy_status": _clean(row.get("occupancy_status")),
                    "sro_registered_rooms": _clean(row.get("#_registered_rooms")),
                    # Same fill-in as the matched case: these records have no
                    # building match at all, so registered_rooms is the only
                    # units signal available.
                    "units": pd.to_numeric(row.get("#_registered_rooms"), errors="coerce"),
                },
                name=_clean(row.get("building_name")),
                source_table="raw_sro",
                source_id=row.get("raw_sro_id"),
            )

    # ---- Rezoning applications ----
    if rezoning is not None:
        rezoning = rezoning.copy()
        rezoning["addr_key"] = rezoning["name"].apply(_rezoning_addr_key)
        matched_mask = rezoning["addr_key"].isin(addr_keys)
        matched = rezoning[matched_mask].drop_duplicates("addr_key")
        unmatched = rezoning[~matched_mask]
        logger.info(
            "Rezoning applications: %d/%d matched an existing building",
            len(matched),
            len(rezoning),
        )

        if not matched.empty:
            lookup = matched.set_index("addr_key")
            hit = df["addr_key"].isin(lookup.index)
            df.loc[hit, "is_rezoning"] = True
            df.loc[hit, "rezoning_status"] = (
                df.loc[hit, "addr_key"].map(lookup["status"]).apply(_clean)
            )
            df.loc[hit, "rezoning_status_group"] = df.loc[hit, "rezoning_status"].apply(
                rezoning_status_group
            )
            df.loc[hit, "rezoning_category"] = (
                df.loc[hit, "addr_key"].map(lookup["category"]).apply(_clean)
            )
            df.loc[hit, "rezoning_status_detail"] = (
                df.loc[hit, "addr_key"].map(lookup["status_detail"]).apply(_clean)
            )
            df.loc[hit, "rezoning_link"] = (
                df.loc[hit, "addr_key"].map(lookup["link"]).apply(_clean)
            )

        for idx, row in unmatched.iterrows():
            lat, lon = row.get("latitude"), row.get("longitude")
            status = _clean(row.get("status"))
            unmatched_records.append(
                {
                    # rezoning_applications.csv's own ID is NOT reliably
                    # unique per row — e.g. RZ285 covers two entirely
                    # different addresses/lat-lons as separate rows (a
                    # multi-site umbrella application) — confirmed via a
                    # real duplicate-key collision during testing.
                    "synthetic_id": f"rezoning-{row.get('id')}-{idx}",
                    "source": "rezoning",
                    "lat": lat,
                    "lon": lon,
                    "address": _clean(row.get("name")),
                    "local_area": _resolve_local_area(lat, lon, boundary_polys),
                    "housing_type": "",
                    "rezoning_status": status,
                    "rezoning_status_group": rezoning_status_group(status),
                    "popup_fields": {
                        "name": _clean(row.get("name")),
                        "status": status,
                        "category": _clean(row.get("category")),
                        "status_detail": _clean(row.get("status_detail")),
                        "link": _clean(row.get("link")),
                    },
                }
            )

    df["housing_type"] = np.where(
        df["is_coop"] & df["is_sro"],
        "co-op, sro",
        np.where(df["is_coop"], "co-op", np.where(df["is_sro"], "sro", "")),
    )

    for rec in extras.values():
        rec["local_area"] = _resolve_local_area(
            rec.get("lat"), rec.get("lon"), boundary_polys
        )

    return OverlayMatchResult(matched=df, unmatched=list(extras.values()))
