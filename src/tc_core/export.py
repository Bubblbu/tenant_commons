"""Exports tc_core's SQLite data for the map.

`export_artifacts()` writes the frontend artifact set (filter_config.json,
marker_metadata.json, building_records.json, blocks.geojson and the local-area
boundary), each with a `schema_version`. That directory is the only interface
between tc_core and the frontend.

VTU membership data (per-building/per-block member counts, membership-year
history, the VTU/non-VTU marker split) is deliberately excluded from every
artifact here — it's sensitive per CLAUDE.md's sensitivity model (§11) and
this is a public-facing export. `reconstruct_points()` still computes it
internally (member_count, has_vtu_member, etc. stay on the DataFrame) since
other internal-only consumers may need it, but none of that reaches
`export_artifacts()`'s output files. See CLAUDE.md's sensitivity-model notes.

Known, deliberate simplification (not a bug): `reconstruct_blocks` emits
every block, citywide, rather than v1's dynamic buffered bbox, so block counts
aren't byte-identical to v1.
"""

from __future__ import annotations

import json
import shutil
import tomllib
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from .geometry import parse_geom
from .ingest.building_names import pick_building_name
from .ingest.overlay_write import BUILDING_OVERLAY_COLUMNS
from .metrics.building_metrics import BUILDING_METRICS, build_building_metrics
from .metrics.membership_metrics import compute_building_member_metrics
from .metrics.portfolios import build_landlord_portfolios
from .metrics.registry_owners import build_registry_owners
from .normalize import sanitize_owner


def reconstruct_points(
    conn: sqlite3.Connection,
    now: pd.Timestamp,
    pid_address_map_path: str | None = None,
    property_managers: set[str] | None = None,
) -> pd.DataFrame:
    buildings = pd.read_sql_query("SELECT * FROM buildings", conn)
    landlords = pd.read_sql_query(
        "SELECT landlord_id, display_name, owner_key FROM landlords", conn
    )
    buildings = buildings.merge(landlords, on="landlord_id", how="left")
    buildings["display_name"] = buildings["display_name"].fillna("(Unknown)")
    buildings["owner_key"] = buildings["owner_key"].fillna("unknown")
    buildings = buildings.rename(
        columns={"building_id": "b_id", "display_name": "licence_holder", "owner_key": "licence_key"}
    )
    buildings["source"] = "building"

    members = pd.read_sql_query(
        "SELECT * FROM vtu_membership WHERE building_id IS NOT NULL", conn
    )
    metrics = compute_building_member_metrics(members, now).rename(
        columns={"building_id": "b_id"}
    )

    merged = buildings.merge(metrics, on="b_id", how="left")
    merged["member_count"] = merged["member_count"].fillna(0).astype(int)
    merged["member_count_all"] = merged["member_count_all"].fillna(0).astype(int)
    merged["has_vtu_member"] = merged["member_count"] > 0
    merged["members_payload"] = merged["members_payload"].apply(
        lambda v: v if isinstance(v, list) else []
    )
    merged["member_share_building"] = np.where(
        (merged["units"] > 0) & merged["units"].notna(),
        np.minimum(merged["member_count"] / merged["units"], 1.0),
        0.0,
    )

    # Two ownership layers (docs/superpowers/specs/2026-09-23-ownership-layers-design.md):
    # the building's own owner — its primary LOTR reporting body, else the
    # licence holder — and its network — the confirmed common_owner cluster
    # its PIDs reach, else the licence holder's group.
    registry = build_registry_owners(conn, pid_address_map_path) if pid_address_map_path else {}
    portfolios = (
        build_landlord_portfolios(conn, pid_address_map_path) if pid_address_map_path else {}
    )
    _assign_ownership(merged, registry, portfolios)
    apply_property_managers(merged, property_managers or set())

    merged = merged[
        [
            "addr_key", "address", "lat", "lon", "units", "year_built", "n_issues", "issues_details",
            "member_count", "has_vtu_member", "member_share_building",
            "owner_name", "owner_key", "owner_source", "registered_owners", "registry_pids",
            "registry_retrieved", "licence_holder", "managed_by", "network_key", "network_name",
            "network_source", "network_name_source", "network_entities",
            "network_properties_on_title", "network_evidence",
            "member_count_all", "members_payload", "value_land",
            "value_bldg", "bldg_land_ratio", "local_area", "b_id", "block_id",
            "latest_membership_year", "source",
            *BUILDING_OVERLAY_COLUMNS,
        ]
    ]
    merged = _append_overlay_housing(conn, merged)
    fill_owner_from_sro(merged)
    fallback_group_to_owner(merged)
    apply_building_names(merged, _load_building_names(conn))

    # Derived post-union (not stored): the matcher's exact expression from
    # ingest/overlays.py, applied uniformly across both origins now that
    # is_coop/is_sro are guaranteed boolean by _append_overlay_housing.
    merged["housing_type"] = np.where(
        merged["is_coop"] & merged["is_sro"],
        "co-op, sro",
        np.where(merged["is_coop"], "co-op", np.where(merged["is_sro"], "sro", "")),
    )
    on_map = merged.groupby("network_key")["b_id"].transform("count")
    merged["network_buildings_on_map"] = [
        None if key == "unknown" else int(count)
        for key, count in zip(merged["network_key"], on_map)
    ]
    return merged


def _assign_ownership(df: pd.DataFrame, registry: dict, portfolios: dict) -> None:
    """Adds the owner_* and network_* columns in place (see the ownership-layers spec)."""
    reg = [registry.get(key) for key in df["addr_key"]]
    port = [portfolios.get(key) for key in df["addr_key"]]
    df["registered_owners"] = [r.owners if r else [] for r in reg]
    df["registry_pids"] = [r.pids if r else [] for r in reg]
    df["registry_retrieved"] = [r.retrieved if r else None for r in reg]
    df["owner_name"] = [r.owners[0] if r else lic for r, lic in zip(reg, df["licence_holder"])]
    df["owner_key"] = df["owner_name"].map(sanitize_owner)
    df["owner_source"] = [
        "registry" if r else ("licence" if key != "unknown" else None)
        for r, key in zip(reg, df["owner_key"])
    ]
    # "net:" namespaces claims-network keys: sanitize_owner() keys never contain
    # ":", so a claims network can't collide with a same-named licence group.
    df["network_key"] = [
        f"net:{p.portfolio_key}" if p else key for p, key in zip(port, df["licence_key"])
    ]
    df["network_name"] = [p.portfolio_name if p else lic for p, lic in zip(port, df["licence_holder"])]
    df["network_source"] = [
        "claims" if p else ("licence" if key != "unknown" else None)
        for p, key in zip(port, df["network_key"])
    ]
    df["network_name_source"] = [p.name_source if p else None for p in port]
    df["network_entities"] = [list(p.entities) if p else None for p in port]
    df["network_properties_on_title"] = [len(p.addr_keys) if p else None for p in port]
    df["network_evidence"] = [dict(p.evidence) if p else None for p in port]


# The SRO inventory abbreviates and truncates names; expand the ones that recur.
# Anything else is shown as published.
SRO_NAME_ALIASES = {
    "BCH": "BC Housing",
    "COV": "City of Vancouver",
    "Atira Property Managem": "Atira Property Management",
    "PHS": "PHS Community Services Society",
    "Lookout": "Lookout Housing and Health Society",
}
# Values that describe a kind of owner or operator rather than naming one
# ("Private" in the operator column means the owner runs the building).
SRO_CATEGORY_WORDS = {"private", "government", "non-profit"}


def clean_sro_name(name) -> str | None:
    """Display form of an SRO owner/operator name; None when it names no one."""
    if name is None or pd.isna(name):
        return None
    text = str(name).strip()
    if not text or text.lower() in SRO_CATEGORY_WORDS:
        return None
    return SRO_NAME_ALIASES.get(text, text)


def fill_owner_from_sro(df: pd.DataFrame) -> None:
    """Expands SRO owner/operator names, and makes the SRO owner the landlord
    of buildings that neither the registry nor a licence names.

    In place. Never replaces a registry or licence owner: when sources
    disagree (BC Housing on title, PHS as licensee), choosing between them is
    the headline rule of the roles spec, not this fallback. Such a building's
    group is itself, as for a licence-only landlord.
    """
    for col in ("sro_owner", "sro_operator"):
        if col in df.columns:
            df[col] = df[col].map(clean_sro_name).astype(object)
    if "sro_owner" not in df.columns:
        return
    fill = (df["owner_key"] == "unknown") & df["sro_owner"].notna()
    df.loc[fill, "owner_name"] = df.loc[fill, "sro_owner"]
    df.loc[fill, "owner_key"] = df.loc[fill, "sro_owner"].map(sanitize_owner)
    df.loc[fill, "owner_source"] = "sro_list"
    group = fill & (df["network_key"] == "unknown")
    df.loc[group, "network_key"] = df.loc[group, "owner_key"]
    df.loc[group, "network_name"] = df.loc[group, "owner_name"]
    df.loc[group, "network_source"] = "sro_list"


def load_property_managers(path: str | None) -> set[str]:
    """Keys of the companies listed in curated/property_managers.toml
    ([[manager]] name = "..."). No file means no known managers."""
    if not path or not Path(path).exists():
        return set()
    data = tomllib.loads(Path(path).read_text())
    return {sanitize_owner(m["name"]) for m in data.get("manager", []) if m.get("name")}


def managers_from_claims(conn: sqlite3.Connection) -> set[str]:
    """Keys of the managing side (entity_a) of confirmed, active managed_by claims."""
    rows = conn.execute(
        "SELECT entity_a FROM ownership_claims "
        "WHERE relationship = 'managed_by' AND status = 'active' AND confidence = 'confirmed'"
    ).fetchall()
    return {sanitize_owner(a) for (a,) in rows}


def apply_property_managers(df: pd.DataFrame, managers: set[str]) -> None:
    """A rental licence held by a known property manager names who runs the
    building, not who owns it (Tribe Rental Management holds licences for
    Greenbrier Holdings' buildings). In place: records the manager in
    `managed_by`; where the licence was the only source for the landlord,
    the building becomes not on record instead. Registry owners and claims
    groups are kept.
    """
    licence_keys = df["licence_holder"].map(sanitize_owner)
    managed = licence_keys.isin(managers)
    df["managed_by"] = df["licence_holder"].where(managed, None).astype(object)
    owner = managed & (df["owner_source"] == "licence")
    df.loc[owner, ["owner_name", "owner_key"]] = ["(Unknown)", "unknown"]
    df.loc[owner, "owner_source"] = None
    # A group that came from the manager's licence falls back to the landlord
    # itself (a group of one), or to not on record when there is none.
    group = managed & (df["network_source"] == "licence")
    df.loc[group, "network_name"] = df.loc[group, "owner_name"]
    df.loc[group, "network_key"] = df.loc[group, "owner_key"]
    df.loc[group, "network_source"] = df.loc[group, "owner_source"]


def _load_building_names(conn: sqlite3.Connection) -> dict[int, list[tuple[str, str]]]:
    names: dict[int, list[tuple[str, str]]] = {}
    try:
        rows = conn.execute("SELECT building_id, name, source_type FROM building_names").fetchall()
    except sqlite3.OperationalError:  # a database built before building_names existed
        return names
    for bid, name, source_type in rows:
        names.setdefault(int(bid), []).append((name, source_type))
    return names


def apply_building_names(df: pd.DataFrame, names: dict[int, list[tuple[str, str]]]) -> None:
    """Adds building_name (the one shown) and other_names. In place.
    Buildings take theirs from building_names; overlay records, whose b_ids
    aren't building ids, keep their own co-op/SRO name."""
    picked = [
        pick_building_name(names.get(int(bid), [])) if src == "building"
        else ((None if pd.isna(hn) or not str(hn).strip() else str(hn)), [])
        for bid, src, hn in zip(df["b_id"], df["source"], df["housing_name"])
    ]
    df["building_name"] = pd.Series([p[0] for p in picked], index=df.index, dtype=object)
    df["other_names"] = pd.Series([p[1] for p in picked], index=df.index, dtype=object)


def fallback_group_to_owner(df: pd.DataFrame) -> None:
    """A landlord with no group (no claims cluster, no licence to group by)
    is its own group of one, so the by-ownership-group view never files a
    known landlord under "not on record". In place."""
    alone = (df["owner_key"] != "unknown") & (df["network_key"] == "unknown")
    df.loc[alone, "network_name"] = df.loc[alone, "owner_name"]
    df.loc[alone, "network_key"] = df.loc[alone, "owner_key"]
    df.loc[alone, "network_source"] = df.loc[alone, "owner_source"]


def _append_overlay_housing(
    conn: sqlite3.Connection, points: pd.DataFrame
) -> pd.DataFrame:
    """Union `overlay_housing` onto the points frame.

    These are SRO/co-op source records that matched no building (see
    ingest/overlay_write.py). They carry coordinates, a name and a housing
    type and little else — no year built, assessed values or owner — so they
    are tagged with a real `source` value rather than being passed off as
    buildings. The one exception is `units`: unmatched SRO records carry a
    registered-room count as a units fallback (a room still houses a tenant;
    see overlay_write.py), so those rows are not blank on the individual
    marker/popup/table. They're still excluded from the building-only
    aggregates in reconstruct_filter_config (dataset totals, block/
    neighbourhood unit sums, the units filter histogram) since they remain
    unverified, non-deduplicated points, not confirmed buildings.
    b_id continues from the buildings table's maximum so the two
    sets never collide. Only the points frame's own columns are kept, so
    overlay_housing's internals (overlay_id, source_row_ids, ingested_at) stay
    out of the export. A record that is both co-op and SRO gets
    source=overlay_coop; housing_type still says "co-op, sro".
    """
    overlay = pd.read_sql_query("SELECT * FROM overlay_housing", conn)
    if overlay.empty:
        combined = points
        for col in ("is_coop", "is_sro", "is_rezoning", "has_vtu_member"):
            if col in combined.columns:
                combined[col] = combined[col].fillna(False).astype(bool)
        return combined

    first_id = int(pd.to_numeric(points["b_id"]).max()) + 1 if len(points) else 1
    overlay["b_id"] = range(first_id, first_id + len(overlay))
    overlay["source"] = [
        "overlay_coop" if bool(c) else "overlay_sro"
        for c in overlay["is_coop"]
    ]
    overlay["owner_name"] = "(Unknown)"
    overlay["owner_key"] = "unknown"
    overlay["licence_holder"] = "(Unknown)"
    overlay["network_key"] = "unknown"
    overlay["network_name"] = "(Unknown)"
    overlay["registered_owners"] = [[] for _ in range(len(overlay))]
    overlay["registry_pids"] = [[] for _ in range(len(overlay))]
    overlay["member_count"] = 0
    overlay["member_count_all"] = 0
    overlay["has_vtu_member"] = False
    overlay["member_share_building"] = 0.0
    overlay["members_payload"] = [[] for _ in range(len(overlay))]
    overlay = overlay.reindex(columns=points.columns)

    combined = pd.concat([points, overlay], ignore_index=True)
    for col in ("is_coop", "is_sro", "is_rezoning", "has_vtu_member"):
        if col in combined.columns:
            combined[col] = combined[col].fillna(False).astype(bool)
    return combined


def resolve_local_area_from_block_numbers(
    blocks_merged: pd.DataFrame, block_numbers_df: pd.DataFrame
) -> pd.Series:
    """Fork of the retired src/sica_mapping/data/spatial.py::resolve_local_area_from_block_numbers
    — see its docstring. Blocks with zero buildings have no local_area to take
    a mode from and default to "(Unknown)"; resolve those from Vancouver Open
    Data's "block-numbers" dataset instead — one point per city block,
    carrying the City's own authoritative geo_local_area. Primary: point-in-
    polygon (a block-numbers point almost always lands inside exactly one of
    our block polygons). Fallback: nearest block-numbers point by centroid
    distance, for the rare block with none landing inside it. Populated
    blocks keep their buildings-derived mode, untouched.
    """
    local_area = blocks_merged["local_area"].copy()
    unknown_mask = local_area == "(Unknown)"
    if not unknown_mask.any() or block_numbers_df.empty:
        return local_area

    bn = block_numbers_df.copy()
    bn["geom_parsed"] = bn["geom"].apply(parse_geom)
    bn = bn.dropna(subset=["geom_parsed", "geo_local_area"])
    if bn.empty:
        return local_area

    block_geoms = list(blocks_merged["geom_parsed"])
    block_ids = blocks_merged["block_id"].to_numpy()
    block_tree = STRtree(block_geoms)

    # Primary: point-in-polygon, one block-numbers point -> one of our blocks.
    matches: dict[int, list[str]] = {}
    for point, area in zip(bn["geom_parsed"], bn["geo_local_area"]):
        for idx in np.atleast_1d(block_tree.query(point)):
            geom = block_geoms[int(idx)]
            if geom.contains(point) or geom.touches(point):
                matches.setdefault(int(block_ids[int(idx)]), []).append(area)
                break
    resolved_by_block = {
        bid: pd.Series(areas).mode().iloc[0] for bid, areas in matches.items()
    }

    # Fallback: nearest block-numbers point by centroid distance, for blocks
    # that got zero points inside their polygon.
    point_tree = STRtree(bn["geom_parsed"].tolist())
    bn_areas = bn["geo_local_area"].to_numpy()
    centroids = blocks_merged["geom_parsed"].apply(
        lambda geom: geom.centroid if geom is not None else None
    )
    for idx in blocks_merged.index[unknown_mask]:
        bid = int(blocks_merged.at[idx, "block_id"])
        resolved = resolved_by_block.get(bid)
        if resolved is None:
            centroid = centroids.at[idx]
            if centroid is not None:
                nearest = point_tree.nearest(centroid)
                resolved = bn_areas[int(nearest)]
        if resolved:
            local_area.at[idx] = resolved
    return local_area


def load_boundary_polygons(geojson_path: str | None) -> list:
    """Every feature's geometry from a boundary GeoJSON (Chinatown, Villages
    Plan Areas), as shapely objects. Missing/empty path -> no polygons, so
    callers get an all-False flag rather than needing their own guard.
    """
    if not geojson_path or not Path(geojson_path).exists():
        return []
    data = json.loads(Path(geojson_path).read_text())
    return [shape(f["geometry"]) for f in data.get("features", []) if f.get("geometry")]


def flag_points_in_polygons(points_df: pd.DataFrame, polygons: list) -> pd.Series:
    """True where a building's point falls inside (or right on the edge of)
    any of `polygons` — the same STRtree point-in-polygon technique as
    resolve_local_area_from_block_numbers above, used here to flag buildings
    within a boundary overlay (e.g. Chinatown) rather than to resolve a
    neighbourhood label.
    """
    flags = pd.Series(False, index=points_df.index)
    if not polygons:
        return flags
    tree = STRtree(polygons)
    for idx, lat, lon in zip(points_df.index, points_df["lat"], points_df["lon"]):
        if pd.isna(lat) or pd.isna(lon):
            continue
        point = Point(lon, lat)
        for gi in np.atleast_1d(tree.query(point)):
            geom = polygons[int(gi)]
            if geom.contains(point) or geom.touches(point):
                flags.at[idx] = True
                break
    return flags


def flag_geoms_intersecting_polygons(geoms: pd.Series, polygons: list) -> pd.Series:
    """True where a block's own polygon overlaps any of `polygons` at all.

    Deliberately derived from the block's own geometry, not from whether any
    of its member buildings are flagged — resolve_local_area_from_block_numbers's
    docstring notes the block<->building join itself has a known accuracy
    bug for a handful of blocks, so inferring a boundary flag from building
    membership would inherit that; testing the block polygon directly avoids
    it and keeps the block layer consistent with the buildings drawn on it.
    """
    flags = pd.Series(False, index=geoms.index)
    if not polygons:
        return flags
    tree = STRtree(polygons)
    for idx, geom in geoms.items():
        if geom is None:
            continue
        for gi in np.atleast_1d(tree.query(geom)):
            if polygons[int(gi)].intersects(geom):
                flags.at[idx] = True
                break
    return flags


def assign_block_labels(blocks_merged: pd.DataFrame) -> pd.Series:
    """Fork of the retired src/sica_mapping/data/spatial.py::assign_block_labels — see its
    docstring. Human-readable "{local_area}-{NN}" labels, reading-order
    (north-to-south, west-to-east) within each neighbourhood. Display-only;
    block_id remains the join/index key everywhere else.
    """
    centroids = blocks_merged["geom_parsed"].apply(
        lambda geom: geom.centroid if geom is not None else None
    )
    order_df = pd.DataFrame(
        {
            "local_area": blocks_merged["local_area"],
            "lat": centroids.apply(lambda c: c.y if c is not None else np.nan),
            "lon": centroids.apply(lambda c: c.x if c is not None else np.nan),
        },
        index=blocks_merged.index,
    )
    labels = pd.Series(index=blocks_merged.index, dtype=object)
    for area, group in order_df.groupby("local_area"):
        ordered = group.sort_values(["lat", "lon"], ascending=[False, True])
        for ordinal, idx in enumerate(ordered.index, start=1):
            labels.at[idx] = f"{area}-{ordinal:02d}"
    return labels


def reconstruct_blocks(conn: sqlite3.Connection, points_df: pd.DataFrame) -> pd.DataFrame:
    # Not bbox-filtered: buildings.csv is already city-wide (not West-End-scoped —
    # see merge.py's notes), so restricting blocks to the static config bbox left
    # most of the actual data — the whole eastside and south of the city — with no
    # block polygons at all.
    blocks_raw = pd.read_sql_query("SELECT block_id, geom FROM blocks", conn)
    agg = (
        points_df.groupby("block_id", dropna=True)
        .agg(
            buildings=("address", "count"),
            total_units=("units", "sum"),
            median_year_built=("year_built", "median"),
            member_buildings=("has_vtu_member", "sum"),
            total_members=("member_count", "sum"),
        )
        .reset_index()
    )
    local_area_by_block = (
        points_df.dropna(subset=["block_id"])
        .groupby("block_id")["local_area"]
        .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "(Unknown)")
        .rename("local_area")
    )
    agg = agg.merge(local_area_by_block, on="block_id", how="left")
    merged = blocks_raw.merge(agg, on="block_id", how="left").fillna(
        {
            "buildings": 0,
            "total_units": 0,
            "median_year_built": np.nan,
            "member_buildings": 0,
            "total_members": 0,
        }
    )
    merged["local_area"] = merged["local_area"].fillna("(Unknown)")
    merged["member_share"] = np.where(
        merged["buildings"] > 0, merged["member_buildings"] / merged["buildings"], 0.0
    )
    merged["geom_parsed"] = merged["geom"].apply(parse_geom)
    block_numbers_df = pd.read_sql_query(
        "SELECT geom, geo_local_area FROM raw_block_numbers", conn
    )
    merged["local_area"] = resolve_local_area_from_block_numbers(merged, block_numbers_df)
    merged["block_label"] = assign_block_labels(merged)
    return merged  # keep `geom` (GeoJSON text) — callers that need shapely use geom_parsed


def reconstruct_filter_config(
    conn: sqlite3.Connection,
    points_df: pd.DataFrame,
    blocks_df: pd.DataFrame,
    now: pd.Timestamp,
) -> dict[str, object]:
    cfg: dict[str, object] = {}

    pts = points_df.copy()
    pts["local_area"] = pts["local_area"].fillna("(Unknown)")
    pts["units"] = pts["units"].fillna(0)

    # Building-describing aggregates (neighbourhood counts/units, dataset
    # totals, building_metrics) must exclude overlay_housing rows (source
    # overlay_sro/overlay_coop) — they're SRO/co-op records with no units,
    # value or membership data, not buildings; counting them here would
    # inflate the map's "Buildings" stat (see _append_overlay_housing).
    # bounds stays over every mapped point below since overlay rows are
    # still drawn on the map.
    buildings_only = (
        pts[pts["source"] == "building"] if "source" in pts.columns else pts
    )

    neighbourhood_counts = (
        buildings_only["local_area"].value_counts().sort_values(ascending=False)
    )
    neighbourhood_units = (
        buildings_only.groupby("local_area")["units"].sum().sort_values(ascending=False)
    )
    cfg["neighbourhoods"] = [
        {"name": area, "count": int(count), "units": int(round(neighbourhood_units.get(area, 0)))}
        for area, count in neighbourhood_counts.items()
    ]

    # Chinatown/Villages Plan Areas: rendered as two more Filters >
    # Neighbourhoods entries after a separator (see legend.ts), not folded
    # into cfg["neighbourhoods"] above since they're boundary overlays a
    # building can belong to *in addition to* its real local_area, not an
    # alternative value of it.
    def _special_area(key: str, name: str, flag_col: str) -> dict:
        flagged = buildings_only[flag_col] if flag_col in buildings_only.columns else pd.Series(dtype=bool)
        return {
            "key": key,
            "name": name,
            "count": int(flagged.sum()),
            "units": int(round(buildings_only.loc[flagged, "units"].sum())) if flagged.any() else 0,
        }

    cfg["special_areas"] = [
        _special_area("chinatown", "Chinatown", "in_chinatown"),
        _special_area("village-plan", "Villages Plan", "in_village_plan"),
    ]

    valid_coords = pts.dropna(subset=["lat", "lon"])
    bounds = None
    if not valid_coords.empty:
        bounds = {
            "lat_min": float(valid_coords["lat"].min()),
            "lat_max": float(valid_coords["lat"].max()),
            "lon_min": float(valid_coords["lon"].min()),
            "lon_max": float(valid_coords["lon"].max()),
            "center_lat": float(valid_coords["lat"].mean()),
            "center_lon": float(valid_coords["lon"].mean()),
        }
    cfg["bounds"] = bounds
    cfg["dataset_totals"] = {
        "buildings": int(len(buildings_only)),
        "units": int(pd.to_numeric(buildings_only["units"], errors="coerce").fillna(0).sum()),
    }

    building_metrics = build_building_metrics(buildings_only)
    cfg["building_metrics"] = building_metrics
    cfg["building_metric_order"] = [
        key for key in BUILDING_METRICS if key in building_metrics
    ]

    cfg["blocks_total_units_max"] = (
        int(blocks_df["total_units"].max()) if not blocks_df.empty else 0
    )
    cfg["licence_year"] = _licence_year(conn)
    return cfg


def _licence_year(conn: sqlite3.Connection) -> int | None:
    """Business-licence data year of this build (raw_buildings.bsns_year)."""
    row = conn.execute("SELECT MAX(bsns_year) FROM raw_buildings").fetchone()
    return int(row[0]) if row and row[0] is not None else None


SCHEMA_VERSION = 1

# ~10 cm. The sources carry 15-decimal coordinates, which made blocks.geojson
# 3.68 MB gzipped — larger than the whole Folium page it replaces. At 6
# decimals it is 1.45 MB; nothing on the map resolves finer.
COORD_DECIMALS = 6


def _round_coords(value):
    """Round every float in a (nested) GeoJSON coordinates array."""
    if isinstance(value, float):
        return round(value, COORD_DECIMALS)
    if isinstance(value, (list, tuple)):
        return [_round_coords(v) for v in value]
    return value


def _round_geometry(geom: dict) -> dict:
    if "coordinates" in geom:
        return {**geom, "coordinates": _round_coords(geom["coordinates"])}
    if "geometries" in geom:  # GeometryCollection
        return {**geom, "geometries": [_round_geometry(g) for g in geom["geometries"]]}
    return geom


def _round_coord(value) -> float | None:
    return None if value is None or pd.isna(value) else round(float(value), COORD_DECIMALS)


def export_artifacts(
    conn: sqlite3.Connection,
    out_dir: str | Path,
    pid_address_map_path: str | None = None,
    boundary_geojson_path: str | None = None,
    villages_geojson_path: str | None = None,
    chinatown_geojson_path: str | None = None,
    now: pd.Timestamp | None = None,
    property_managers_path: str | None = None,
) -> None:
    """Write the complete frontend artifact set.

    This is the one-directional contract: every value the map displays is
    produced here. Each file carries a schema_version so a frontend built
    against an older shape fails loudly instead of rendering an empty map.
    """
    if now is None:
        now = pd.Timestamp.now(tz="UTC")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    points_df = reconstruct_points(
        conn, now, pid_address_map_path,
        load_property_managers(property_managers_path) | managers_from_claims(conn),
    )

    # Chinatown/Villages Plan Areas double as filterable "special areas"
    # (Filters > Neighbourhoods, after the separator) alongside local_area —
    # a building/block can be in a real neighbourhood *and* one of these
    # overlays at once, so they're flags of their own rather than folded
    # into local_area.
    chinatown_polygons = load_boundary_polygons(chinatown_geojson_path)
    village_polygons = load_boundary_polygons(villages_geojson_path)
    points_df["in_chinatown"] = flag_points_in_polygons(points_df, chinatown_polygons)
    points_df["in_village_plan"] = flag_points_in_polygons(points_df, village_polygons)

    blocks_df = reconstruct_blocks(conn, points_df)
    blocks_df["in_chinatown"] = flag_geoms_intersecting_polygons(
        blocks_df["geom_parsed"], chinatown_polygons
    )
    blocks_df["in_village_plan"] = flag_geoms_intersecting_polygons(
        blocks_df["geom_parsed"], village_polygons
    )

    filter_cfg = reconstruct_filter_config(conn, points_df, blocks_df, now)

    _write_json(
        out_dir / "filter_config.json",
        {"schema_version": SCHEMA_VERSION, **filter_cfg},
    )
    _write_json(
        out_dir / "marker_metadata.json",
        {
            "schema_version": SCHEMA_VERSION,
            "markers": _marker_records(points_df),
        },
    )
    _write_json(
        out_dir / "building_records.json",
        {
            "schema_version": SCHEMA_VERSION,
            **_building_records(points_df),
        },
    )
    _write_json(out_dir / "blocks.geojson", _blocks_feature_collection(blocks_df))

    if boundary_geojson_path:
        shutil.copyfile(
            boundary_geojson_path, out_dir / "local-area-boundary.geojson"
        )

    if villages_geojson_path:
        shutil.copyfile(
            villages_geojson_path, out_dir / "villages_plan_areas.geojson"
        )

    if chinatown_geojson_path:
        shutil.copyfile(
            chinatown_geojson_path, out_dir / "chinatown_boundary.geojson"
        )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def _blocks_feature_collection(blocks_df: pd.DataFrame) -> dict:
    """Emit stored GeoJSON geometry directly — no shapely round trip.

    `blocks.geom` is already GeoJSON text in SQLite, so parsing it into a
    shapely object only to re-serialize via __geo_interface__ is wasted work.
    """
    property_cols = [
        "block_id",
        "buildings",
        "total_units",
        "median_year_built",
        "local_area",
        "block_label",
        "in_chinatown",
        "in_village_plan",
    ]
    features = []
    for _, row in blocks_df.iterrows():
        geom = row.get("geom")
        if geom is None:
            continue
        if isinstance(geom, str):
            geom = json.loads(geom)
        features.append(
            {
                "type": "Feature",
                "geometry": _round_geometry(geom),
                "properties": {
                    col: (None if pd.isna(row.get(col)) else row.get(col))
                    for col in property_cols
                    if col in blocks_df.columns
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "schema_version": SCHEMA_VERSION,
        "features": features,
    }


def _marker_records(points_df: pd.DataFrame) -> list[dict]:
    """Per-building marker data, including coordinates.

    Styling (radius, colours, rings) is presentation and is computed by the
    frontend (frontend/src/markers.ts); these records carry only data.
    """
    records = []
    for _, r in points_df.iterrows():
        records.append(
            {
                "b_id": int(r["b_id"]),
                "lat": _round_coord(r["lat"]),
                "lon": _round_coord(r["lon"]),
                "owner_key": r.get("owner_key"),
                "network_key": r.get("network_key"),
                "block_id": None if pd.isna(r.get("block_id")) else int(r["block_id"]),
                "units": None if pd.isna(r.get("units")) else int(r["units"]),
                "year_built": None
                if pd.isna(r.get("year_built"))
                else int(r["year_built"]),
                "local_area": r.get("local_area"),
                "housing_type": r.get("housing_type") or "",
                "n_issues": None if pd.isna(r.get("n_issues")) else int(r["n_issues"]),
                "source": r.get("source", "building"),
            }
        )
    return records


# building_records.json's columns, in order. An explicit list, not "every
# column of points_df": the frontend's CSV export writes these verbatim, so
# lineage/ingest internals and — per the public/sensitive filter (spec
# §12) — VTU membership data must never reach it. Ownership is two layers:
# owner_* (the building's own owner) and network_* (its landlord network);
# claim provenance is public only as source-type counts, never notes.
BUILDING_RECORD_COLUMNS = [
    "b_id", "address", "building_name", "other_names", "local_area", "block_id", "units",
    "year_built", "owner_name", "owner_key", "owner_source",
    "registered_owners", "registry_pids", "registry_retrieved", "licence_holder", "managed_by",
    "network_key", "network_name", "network_source", "network_name_source",
    "network_entities", "network_buildings_on_map", "network_properties_on_title",
    "network_evidence",
    "value_land", "value_bldg", "bldg_land_ratio",
    "housing_type", "n_issues", "issues_details", "source",
    "lat", "lon",
    "in_chinatown", "in_village_plan",
    *BUILDING_OVERLAY_COLUMNS,
]


def _building_records(points_df: pd.DataFrame) -> dict:
    """Full per-building record set — the popup and the table both read this."""
    df = points_df.copy()
    records = {}
    for _, r in df.iterrows():
        rec = {
            c: (None if isinstance(r[c], float) and pd.isna(r[c]) else r[c])
            for c in BUILDING_RECORD_COLUMNS
        }
        for c in ("lat", "lon"):
            if c in rec:
                rec[c] = _round_coord(rec[c])
        records[str(int(r["b_id"]))] = rec
    return {"columns": list(BUILDING_RECORD_COLUMNS), "records": records}
