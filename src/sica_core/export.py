"""Exports sica_core's SQLite data for the map.

`export_artifacts()` writes the frontend artifact set (filter_config.json,
marker_metadata.json, building_records.json, blocks.geojson and the local-area
boundary), each with a `schema_version`. That directory is the only interface
between sica_core and the frontend.

This reproduces the same full data the current map already shows (including
VTU membership counts) — no public/sensitive field redaction here. That's a
separate, later piece of work for whenever an actual public-facing map
exists to feed; see CLAUDE.md's sensitivity-model notes.

Known, deliberate simplification (not a bug): `reconstruct_blocks` emits
every block, citywide, rather than v1's dynamic buffered bbox, so block counts
aren't byte-identical to v1.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.strtree import STRtree

from .building_metrics import BUILDING_METRICS, _summarize_metric, build_building_metrics
from .geometry import parse_geom
from .ingest.overlay_write import BUILDING_OVERLAY_COLUMNS
from .membership_metrics import compute_building_member_metrics, membership_filter_config
from .portfolios import build_landlord_portfolios


def reconstruct_points(
    conn: sqlite3.Connection, now: pd.Timestamp, pid_address_map_path: str | None = None
) -> pd.DataFrame:
    buildings = pd.read_sql_query("SELECT * FROM buildings", conn)
    landlords = pd.read_sql_query(
        "SELECT landlord_id, display_name, owner_key FROM landlords", conn
    )
    buildings = buildings.merge(landlords, on="landlord_id", how="left")
    buildings["display_name"] = buildings["display_name"].fillna("(Unknown)")
    buildings["owner_key"] = buildings["owner_key"].fillna("unknown")
    buildings = buildings.rename(
        columns={"building_id": "b_id", "display_name": "owner_group"}
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

    # Claims-derived landlord portfolios (CLAUDE.md Phase 1: "wire in claims-
    # derived landlord clustering"), joined onto buildings via PID rather than
    # the vhd-derived owner_group label — see portfolios.py's module docstring
    # for why. Only buildings reached by a confirmed common_owner cluster get
    # a non-null portfolio_name; where present it becomes the displayed/
    # grouped owner_group/owner_key outright (for now — see portfolios.py),
    # so search, the Landlords tab, and hover-highlight all pick it up with
    # no separate code path. portfolio_building_count/portfolio_entities are
    # kept alongside for the popup's "N buildings, M linked entities" detail.
    portfolios = (
        build_landlord_portfolios(conn, pid_address_map_path)
        if pid_address_map_path
        else {}
    )
    merged["portfolio_name"] = merged["addr_key"].map(
        lambda k: portfolios[k].portfolio_name if k in portfolios else None
    )
    merged["portfolio_building_count"] = merged["addr_key"].map(
        lambda k: len(portfolios[k].addr_keys) if k in portfolios else None
    )
    merged["portfolio_entities"] = merged["addr_key"].map(
        lambda k: portfolios[k].entities if k in portfolios else None
    )
    portfolio_key = merged["addr_key"].map(
        lambda k: portfolios[k].portfolio_key if k in portfolios else None
    )
    merged["owner_group"] = merged["portfolio_name"].fillna(merged["owner_group"])
    merged["owner_key"] = portfolio_key.fillna(merged["owner_key"])

    merged = merged[
        [
            "addr_key", "address", "lat", "lon", "units", "year_built", "n_issues",
            "member_count", "has_vtu_member", "member_share_building", "owner_group",
            "owner_key", "member_count_all", "members_payload", "value_land",
            "value_bldg", "bldg_land_ratio", "local_area", "b_id", "block_id",
            "latest_membership_year", "portfolio_name", "portfolio_building_count",
            "portfolio_entities", "source",
            *BUILDING_OVERLAY_COLUMNS,
        ]
    ]
    merged = _append_overlay_housing(conn, merged)

    # Derived post-union (not stored): the matcher's exact expression from
    # ingest/overlays.py, applied uniformly across both origins now that
    # is_coop/is_sro are guaranteed boolean by _append_overlay_housing.
    merged["housing_type"] = np.where(
        merged["is_coop"] & merged["is_sro"],
        "co-op, sro",
        np.where(merged["is_coop"], "co-op", np.where(merged["is_sro"], "sro", "")),
    )
    return merged


def _append_overlay_housing(
    conn: sqlite3.Connection, points: pd.DataFrame
) -> pd.DataFrame:
    """Union `overlay_housing` onto the points frame.

    These are SRO/co-op source records that matched no building (see
    ingest/overlay_write.py). They carry coordinates, a name and a housing
    type and nothing else — no units, year built, assessed values or owner —
    so they are tagged with a real `source` value rather than being passed off
    as buildings. b_id continues from the buildings table's maximum so the two
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
    overlay["owner_group"] = "(Unknown)"
    overlay["owner_key"] = "unknown"
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
    members = pd.read_sql_query(
        "SELECT * FROM vtu_membership WHERE building_id IS NOT NULL", conn
    )
    cfg = dict(membership_filter_config(members, now))

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
        "members": int(buildings_only["member_count"].sum()),
        "units": int(pd.to_numeric(buildings_only["units"], errors="coerce").fillna(0).sum()),
        "vtu_buildings": int(buildings_only["has_vtu_member"].sum()),
    }

    building_metrics = build_building_metrics(buildings_only)
    cfg["building_metrics"] = building_metrics
    cfg["building_metric_order"] = [
        key for key in BUILDING_METRICS if key in building_metrics
    ]

    # Rendered with the same dual-slider component as building_metrics, but kept
    # out of that dict so it doesn't also show up under the "Buildings" filter
    # section — it's rendered into its own container under "Membership" instead.
    cfg["membership_year_metric"] = _summarize_metric(
        pts["latest_membership_year"],
        meta={
            "label": "Membership year",
            "format": "number",
            "type": "int",
            "step": 1,
            "attr": "latest-membership-year",
            "bins": 12,
        },
    )

    cfg["blocks_total_units_max"] = (
        int(blocks_df["total_units"].max()) if not blocks_df.empty else 0
    )
    return cfg


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
    now: pd.Timestamp | None = None,
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

    points_df = reconstruct_points(conn, now, pid_address_map_path)
    blocks_df = reconstruct_blocks(conn, points_df)
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
        "member_buildings",
        "total_members",
        "member_share",
        "local_area",
        "block_label",
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
        has_member = bool(r.get("has_vtu_member"))
        records.append(
            {
                "b_id": int(r["b_id"]),
                "lat": _round_coord(r["lat"]),
                "lon": _round_coord(r["lon"]),
                "owner_key": r.get("owner_key"),
                "block_id": None if pd.isna(r.get("block_id")) else int(r["block_id"]),
                "units": None if pd.isna(r.get("units")) else int(r["units"]),
                "year_built": None
                if pd.isna(r.get("year_built"))
                else int(r["year_built"]),
                "local_area": r.get("local_area"),
                "is_vtu": has_member,
                "member_count": int(r.get("member_count") or 0),
                "housing_type": r.get("housing_type") or "",
                "source": r.get("source", "building"),
            }
        )
    return records


# building_records.json's columns, in order. An explicit list, not "every
# column of points_df": the frontend's CSV export writes these verbatim, so
# lineage/ingest internals and per-member payloads must never reach it. The
# first 18 are the Folium map's table columns, in its order; the rest are the
# popup's and the overlay detail. This is also where the public/sensitive
# filter (spec §12) will go.
BUILDING_RECORD_COLUMNS = [
    "b_id", "address", "local_area", "block_id", "units", "member_count",
    "year_built", "owner_group", "owner_key", "member_count_all", "value_land",
    "value_bldg", "bldg_land_ratio", "has_vtu_member", "latest_membership_year",
    "housing_type", "member_share_pct", "source",
    "lat", "lon",
    "portfolio_name", "portfolio_building_count", "portfolio_entities",
    *BUILDING_OVERLAY_COLUMNS,
]


def _building_records(points_df: pd.DataFrame) -> dict:
    """Full per-building record set — the popup and the table both read this."""
    df = points_df.copy()
    # Whole percent, rounded half-to-even like the Folium table's pandas round.
    df["member_share_pct"] = [
        int(round(float(v) * 100)) if pd.notna(v) else 0
        for v in df["member_share_building"]
    ]
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
