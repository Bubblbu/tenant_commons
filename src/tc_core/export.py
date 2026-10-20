"""Exports tc_core's SQLite data for the map.

`export_artifacts()` writes the frontend artifact set (filter_config.json,
marker_metadata.json, building_records.json, networks.json, blocks.geojson,
the local-area boundary and overlay_areas.geojson), each JSON file of our
own with a `schema_version`. building_records.json
and networks.json are validated against tc_core/contract.py. That directory is the only interface
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
import math
import shutil
import sqlite3
import tomllib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
from shapely.geometry import Point, mapping, shape
from shapely.strtree import STRtree

from .claims import resolve_entity_clusters
from .contract import SCHEMA_VERSION, BuildingRecordsFile, NetworksFile
from .db import query_frame
from .export_contract import LandShares, build_building, build_networks, land_share
from .export_parties import match_key
from .geometry import parse_geom
from .ingest.building_names import pick_building_name
from .ingest.overlay_write import BUILDING_OVERLAY_COLUMNS
from .metrics.building_metrics import BUILDING_METRICS, build_building_metrics
from .metrics.membership_metrics import compute_building_member_metrics
from .metrics.portfolios import build_landlord_portfolios
from .metrics.registry_owners import (
    build_interest_holders,
    build_registry_owners,
    build_registry_searches,
    building_pids,
    entity_kinds,
)
from .normalize import sanitize_owner
from .overlay_areas import OverlayArea, load_area_features
from .sro_names import SroName, load_sro_names
from .sro_names import clean_sro_name as _clean_sro_name


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _objects(values) -> pl.Series:
    """A column of Python lists/dicts, passed through to the JSON as they are."""
    return pl.Series(list(values), dtype=pl.Object)


def _mode(values) -> object | None:
    """Most frequent non-missing value; ties go to the smallest (pandas'
    mode().iloc[0])."""
    counts = Counter(v for v in values if not _missing(v))
    if not counts:
        return None
    top = max(counts.values())
    return min(v for v, n in counts.items() if n == top)


def _where(df: pl.DataFrame, mask: pl.Expr, **values) -> pl.DataFrame:
    """Set each column to its value (an expression or a constant) where
    `mask` holds, evaluated against `df` as it is."""
    return df.with_columns(
        pl.when(mask)
        .then(v if isinstance(v, pl.Expr) else pl.lit(v) if v is not None else pl.lit(None, dtype=df.schema[c]))
        .otherwise(pl.col(c))
        .alias(c)
        for c, v in values.items()
    )


def reconstruct_points(
    conn: sqlite3.Connection,
    now: datetime,
    pid_address_map_path: str | None = None,
    property_managers: set[str] | None = None,
    listing_aliases: dict[str, str] | None = None,
) -> pl.DataFrame:
    # Counts are integers; values and years (medians, so possibly fractional)
    # are floats whatever this build's data happens to hold.
    buildings = query_frame(conn, "SELECT * FROM buildings").with_columns(
        pl.col("building_id", "landlord_id", "block_id", "units", "n_issues").cast(pl.Int64),
        pl.col("year_built", "value_land", "value_bldg", "bldg_land_ratio", "lat", "lon").cast(pl.Float64),
    )
    landlords = query_frame(
        conn, "SELECT landlord_id, display_name, owner_key FROM landlords"
    ).with_columns(pl.col("landlord_id").cast(pl.Int64), pl.col("display_name", "owner_key").cast(pl.String))
    buildings = (
        buildings.join(landlords, on="landlord_id", how="left", maintain_order="left")
        .with_columns(
            pl.col("display_name").fill_null("(Unknown)"),
            pl.col("owner_key").fill_null("unknown"),
            source=pl.lit("building"),
        )
        .rename({"building_id": "b_id", "display_name": "licence_holder", "owner_key": "licence_key"})
    )

    members = query_frame(conn, "SELECT * FROM vtu_membership WHERE building_id IS NOT NULL")
    metrics = compute_building_member_metrics(members, now).rename({"building_id": "b_id"})

    merged = buildings.join(
        metrics.with_columns(pl.col("b_id").cast(pl.Int64)), on="b_id", how="left", maintain_order="left"
    ).with_columns(
        pl.col("member_count").fill_null(0),
        pl.col("member_count_all").fill_null(0),
    )
    merged = merged.with_columns(
        has_vtu_member=pl.col("member_count") > 0,
        members_payload=_objects(v if isinstance(v, list) else [] for v in merged["members_payload"].to_list()),
        member_share_building=pl.when(pl.col("units") > 0)
        .then(pl.min_horizontal(pl.col("member_count") / pl.col("units"), pl.lit(1.0)))
        .otherwise(0.0),
    )

    # Two ownership layers (docs/superpowers/specs/2026-09-23-ownership-layers-design.md):
    # the building's own owner — its primary LOTR reporting body, else the
    # licence holder — and its network — the confirmed common_owner cluster
    # its PIDs reach, else the licence holder's group.
    registry = build_registry_owners(conn, pid_address_map_path) if pid_address_map_path else {}
    portfolios = (
        build_landlord_portfolios(conn, pid_address_map_path) if pid_address_map_path else {}
    )
    merged = _assign_ownership(merged, registry, portfolios)
    # "Searched the registry, no filing": public as a date only (search notes stay internal).
    no_filing = build_registry_searches(conn, pid_address_map_path) if pid_address_map_path else {}
    # Who stands behind the owners: name and interest type only (spec 2026-10-08 §3).
    holders = build_interest_holders(conn, pid_address_map_path) if pid_address_map_path else {}
    parcels = building_pids(conn, pid_address_map_path) if pid_address_map_path else {}
    building_listings = _load_building_listings(conn, listing_aliases or {})
    merged = merged.with_columns(
        registry_no_filing=pl.Series(
            [None if registry.get(key) else no_filing.get(key) for key in merged["addr_key"]],
            dtype=pl.String,
        ),
        listings=_objects(building_listings.get(int(b), []) for b in merged["b_id"]),
        interest_holders=_objects(holders.get(key, []) for key in merged["addr_key"]),
    )
    merged = apply_property_managers(merged, property_managers or set())

    merged = merged.select(
        [
            "addr_key", "address", "lat", "lon", "units", "building_source", "year_built", "n_issues",
            "issues_details",
            "member_count", "has_vtu_member", "member_share_building",
            "owner_name", "owner_key", "owner_source", "registered_owners", "registry_pids",
            "registry_retrieved", "registry_no_filing", "registry_owner_pids", "interest_holders",
            "licence_holder", "managed_by",
            "managed_by_source", "listings", "network_key", "network_name",
            "network_source", "network_name_source", "network_entities",
            "network_properties_on_title", "network_evidence",
            "member_count_all", "members_payload", "value_land",
            "value_bldg", "bldg_land_ratio", "local_area", "b_id", "block_id",
            "latest_membership_year", "source",
            *BUILDING_OVERLAY_COLUMNS,
        ]
    )
    merged = _append_overlay_housing(conn, merged)
    # Overlay records have no listings or registry data; keep these columns lists throughout.
    merged = merged.with_columns(
        _objects(v if isinstance(v, list) else [] for v in merged[col].to_list()).alias(col)
        for col in ("listings", "registry_owner_pids", "interest_holders")
    )
    # Every known PID, buildings and overlay records alike, by address.
    merged = merged.with_columns(pids=_objects(parcels.get(k, []) for k in merged["addr_key"]))
    merged = apply_registry_to_overlays(merged, registry, portfolios, holders, no_filing)
    merged = fill_owner_from_sro(merged)
    merged = regroup_registry_owners(merged)
    merged = fallback_group_to_owner(merged)
    merged = apply_building_names(merged, _load_building_names(conn))

    # Derived post-union (not stored): the matcher's exact expression from
    # ingest/overlays.py, applied uniformly across both origins now that
    # is_coop/is_sro are guaranteed boolean by _append_overlay_housing.
    return merged.with_columns(
        housing_type=pl.when(pl.col("is_coop") & pl.col("is_sro"))
        .then(pl.lit("co-op, sro"))
        .when(pl.col("is_coop"))
        .then(pl.lit("co-op"))
        .when(pl.col("is_sro"))
        .then(pl.lit("sro"))
        .otherwise(pl.lit("")),
        network_buildings_on_map=pl.when(pl.col("network_key") == "unknown")
        .then(None)
        .otherwise(pl.len().over("network_key"))
        .cast(pl.Int64),
    )


def _assign_ownership(df: pl.DataFrame, registry: dict, portfolios: dict) -> pl.DataFrame:
    """Adds the owner_* and network_* columns (see the ownership-layers spec)."""
    reg = [registry.get(key) for key in df["addr_key"]]
    port = [portfolios.get(key) for key in df["addr_key"]]
    owner_name = [r.owners[0] if r else lic for r, lic in zip(reg, df["licence_holder"])]
    owner_key = [sanitize_owner(name) for name in owner_name]
    # "net:" namespaces claims-network keys: sanitize_owner() keys never contain
    # ":", so a claims network can't collide with a same-named licence group.
    network_key = [f"net:{p.portfolio_key}" if p else key for p, key in zip(port, df["licence_key"])]
    text = lambda values: pl.Series(list(values), dtype=pl.String)
    return df.with_columns(
        registered_owners=_objects(r.owners if r else [] for r in reg),
        registry_pids=_objects(r.pids if r else [] for r in reg),
        registry_owner_pids=_objects(
            [{"name": n, "pids": r.owner_pids.get(n, [])} for n in r.owners] if r else []
            for r in reg
        ),
        registry_retrieved=text(r.retrieved if r else None for r in reg),
        owner_name=text(owner_name),
        owner_key=text(owner_key),
        owner_source=text(
            "registry" if r else ("licence" if key != "unknown" else None)
            for r, key in zip(reg, owner_key)
        ),
        network_key=text(network_key),
        network_name=text(p.portfolio_name if p else lic for p, lic in zip(port, df["licence_holder"])),
        network_source=text(
            "claims" if p else ("licence" if key != "unknown" else None)
            for p, key in zip(port, network_key)
        ),
        network_name_source=text(p.name_source if p else None for p in port),
        network_entities=_objects(list(p.entities) if p else None for p in port),
        network_properties_on_title=pl.Series(
            [len(p.addr_keys) if p else None for p in port], dtype=pl.Int64
        ),
        network_evidence=_objects(dict(p.evidence) if p else None for p in port),
    )


def clean_sro_name(name) -> str | None:
    """Display form of an SRO owner/operator name; None when it names no one
    (see sro_names.py::clean_sro_name)."""
    return _clean_sro_name(None if _missing(name) else name)


def _sro_operator(operator: str | None, owner: SroName | None, names: dict[str, SroName]) -> str | None:
    """The operator as corrected; where the inventory names none, the lessee
    or operator the owner's corrected entry names (306 Jackson Ave: Chris Wall)."""
    if operator is None:
        return owner.manager if owner else None
    return names[operator].owners[0] if operator in names else operator


def fill_owner_from_sro(df: pl.DataFrame, names: dict[str, SroName] | None = None) -> pl.DataFrame:
    """Expands SRO owner/operator names, and makes the SRO inventory's owner
    the building's owner wherever the registry doesn't name one — over a
    licence holder too (spec 2026-10-08 §3: BC Housing owns Marble Arch; PHS
    only holds the licence). A licence-name group becomes the SRO owner's own
    name group. Registry owners and claims networks are never replaced.

    `names` (sro_names.txt) corrects published names: the first of joint
    owners becomes sro_owner and all of them sro_owners; a named lessee or
    operator fills sro_operator where the inventory names none.
    """
    names = load_sro_names() if names is None else names
    df = df.with_columns(
        pl.col(col).map_elements(clean_sro_name, return_dtype=pl.String, skip_nulls=False)
        for col in ("sro_owner", "sro_operator")
        if col in df.columns
    )
    if "sro_owner" not in df.columns:
        return df
    corrected = [names.get(o) if o is not None else None for o in df["sro_owner"]]
    df = df.with_columns(
        sro_owners=_objects(
            (c.owners if c else [o]) if o is not None else [] for o, c in zip(df["sro_owner"], corrected)
        ),
        sro_owner=pl.Series([c.owners[0] if c else o for o, c in zip(df["sro_owner"], corrected)], dtype=pl.String),
        sro_operator=pl.Series(
            [_sro_operator(op, c, names) for op, c in zip(df["sro_operator"], corrected)], dtype=pl.String
        ),
    )
    df = df.with_columns(
        _fill=pl.col("sro_owner").is_not_null()
        & ((pl.col("owner_key") == "unknown") | (pl.col("owner_source") == "licence")).fill_null(False)
    )
    df = _where(
        df,
        pl.col("_fill"),
        owner_name=pl.col("sro_owner"),
        owner_key=pl.col("sro_owner").map_elements(sanitize_owner, return_dtype=pl.String),
        owner_source="sro_list",
    )
    group = pl.col("_fill") & (
        (pl.col("network_key") == "unknown") | (pl.col("network_source") == "licence")
    ).fill_null(False)
    return _where(
        df, group, network_key=pl.col("owner_key"), network_name=pl.col("owner_name"),
        network_source="sro_list",
    ).drop("_fill")


def load_property_managers(path: str | None) -> set[str]:
    """Keys of the companies listed in curated/property_managers.toml
    ([[manager]] name = "..."). No file means no known managers."""
    if not path or not Path(path).exists():
        return set()
    data = tomllib.loads(Path(path).read_text())
    return {sanitize_owner(m["name"]) for m in data.get("manager", []) if m.get("name")}


def load_listing_aliases(path: str | None) -> dict[str, str]:
    """Feed company name key -> the manager's name in property_managers.toml.
    A feed may name the company differently ("Tribe Rentals"); an entry lists
    those names as listing_names = [...]. Each entry's own name maps to itself."""
    if not path or not Path(path).exists():
        return {}
    data = tomllib.loads(Path(path).read_text())
    aliases: dict[str, str] = {}
    for m in data.get("manager", []):
        name = m.get("name")
        if not name:
            continue
        for alias in [name, *m.get("listing_names", [])]:
            aliases[sanitize_owner(alias)] = name
    return aliases


def _load_building_listings(
    conn: sqlite3.Connection, aliases: dict[str, str]
) -> dict[int, list[dict]]:
    """building_id -> [{by, url, seen}], one entry per company, a known
    manager under its property_managers.toml name. Public: each is the
    company's own page. Listing ids stay in the database."""
    out: dict[int, list[dict]] = {}
    try:
        rows = conn.execute(
            "SELECT building_id, manager, url, last_seen FROM building_listings "
            "ORDER BY building_id, listing_row_id"
        ).fetchall()
    except sqlite3.OperationalError:  # a database built before building_listings existed
        return out
    for bid, manager, url, seen in rows:
        by = aliases.get(sanitize_owner(manager), manager)
        entries = out.setdefault(int(bid), [])
        if not any(e["by"] == by for e in entries):
            entries.append({"by": by, "url": url, "seen": seen})
    return out


def managers_from_claims(conn: sqlite3.Connection) -> set[str]:
    """Keys of the managing side (entity_a) of confirmed, active managed_by claims."""
    rows = conn.execute(
        "SELECT entity_a FROM ownership_claims "
        "WHERE relationship = 'managed_by' AND status = 'active' AND confidence = 'confirmed'"
    ).fetchall()
    return {sanitize_owner(a) for (a,) in rows}


def apply_property_managers(df: pl.DataFrame, managers: set[str]) -> pl.DataFrame:
    """A rental licence held by a known property manager names who runs the
    building, not who owns it (Tribe Rental Management holds licences for
    Greenbrier Holdings' buildings). Records the manager in
    `managed_by`; where the licence was the only source for the landlord,
    the building becomes not on record instead. Registry owners and claims
    groups are kept. Otherwise a known manager's current listing names the
    manager (`managed_by_source` "listing") and changes nothing else.
    """
    managed = pl.Series(
        [sanitize_owner(h) in managers for h in df["licence_holder"]], dtype=pl.Boolean
    )
    df = df.with_columns(
        _managed=managed,
        managed_by=pl.when(managed).then(pl.col("licence_holder")).otherwise(None),
        managed_by_source=pl.when(managed).then(pl.lit("licence")).otherwise(None),
    )
    owner = pl.col("_managed") & (pl.col("owner_source") == "licence").fill_null(False)
    df = _where(df, owner, owner_name="(Unknown)", owner_key="unknown", owner_source=None)
    # A group that came from the manager's licence falls back to the landlord
    # itself (a group of one), or to not on record when there is none.
    group = pl.col("_managed") & (pl.col("network_source") == "licence").fill_null(False)
    df = _where(
        df, group, network_name=pl.col("owner_name"), network_key=pl.col("owner_key"),
        network_source=pl.col("owner_source"),
    ).drop("_managed")
    if "listings" not in df.columns:
        return df
    listed = pl.Series(
        [
            next(
                (e["by"] for e in (ls if isinstance(ls, list) else [])
                 if sanitize_owner(e["by"]) in managers),
                None,
            )
            for ls in df["listings"].to_list()
        ],
        dtype=pl.String,
    )
    fill = pl.col("managed_by").is_null() & listed.is_not_null()
    return _where(df, fill, managed_by=pl.lit(listed), managed_by_source="listing")


def _load_building_names(conn: sqlite3.Connection) -> dict[int, list[tuple[str, str]]]:
    names: dict[int, list[tuple[str, str]]] = {}
    try:
        rows = conn.execute("SELECT building_id, name, source_type FROM building_names").fetchall()
    except sqlite3.OperationalError:  # a database built before building_names existed
        return names
    for bid, name, source_type in rows:
        names.setdefault(int(bid), []).append((name, source_type))
    return names


def apply_building_names(df: pl.DataFrame, names: dict[int, list[tuple[str, str]]]) -> pl.DataFrame:
    """Adds building_name (the one shown) and other_names.
    Buildings take theirs from building_names; overlay records, whose b_ids
    aren't building ids, keep their own co-op/SRO name."""
    picked = [
        pick_building_name(names.get(int(bid), [])) if src == "building"
        else ((None if _missing(hn) or not str(hn).strip() else str(hn)), [])
        for bid, src, hn in zip(df["b_id"], df["source"], df["housing_name"])
    ]
    return df.with_columns(
        building_name=pl.Series([p[0] for p in picked], dtype=pl.String),
        other_names=_objects(p[1] for p in picked),
    )


def apply_registry_to_overlays(
    df: pl.DataFrame, registry: dict, portfolios: dict, holders: dict, no_filing: dict
) -> pl.DataFrame:
    """SRO/co-op points that matched no building get the registry layers
    buildings get in _assign_ownership: the owner on title, who stands behind
    it, a claims network (reached through a filing or the SRO owner's name)
    and the search date. Before this, a researched PID under an overlay
    point (139 E Cordova St) never reached the map. They have no licence,
    so nothing else changes."""
    overlay = [src != "building" for src in df["source"]]
    if not any(overlay):
        return df
    keys = df["addr_key"].to_list()
    cols = {c: df[c].to_list() for c in (
        "owner_name", "owner_key", "owner_source", "registered_owners", "registry_pids",
        "registry_retrieved", "registry_owner_pids", "interest_holders", "registry_no_filing",
        "network_key", "network_name", "network_source", "network_name_source",
        "network_entities", "network_properties_on_title", "network_evidence",
    )}
    for i, key in enumerate(keys):
        if not overlay[i]:
            continue
        reg, port = registry.get(key), portfolios.get(key)
        cols["interest_holders"][i] = holders.get(key, [])
        if reg:
            cols["owner_name"][i] = reg.owners[0]
            cols["owner_key"][i] = sanitize_owner(reg.owners[0])
            cols["owner_source"][i] = "registry"
            cols["registered_owners"][i] = reg.owners
            cols["registry_pids"][i] = reg.pids
            cols["registry_retrieved"][i] = reg.retrieved
            cols["registry_owner_pids"][i] = [{"name": n, "pids": reg.owner_pids.get(n, [])} for n in reg.owners]
        else:
            cols["registry_no_filing"][i] = no_filing.get(key)
        # A claims network reaches a point through a filing or its SRO owner's name.
        if port:
            cols["network_key"][i] = f"net:{port.portfolio_key}"
            cols["network_name"][i] = port.portfolio_name
            cols["network_source"][i] = "claims"
            cols["network_name_source"][i] = port.name_source
            cols["network_entities"][i] = list(port.entities)
            cols["network_properties_on_title"][i] = len(port.addr_keys)
            cols["network_evidence"][i] = dict(port.evidence)
    objects = {"registered_owners", "registry_pids", "registry_owner_pids", "interest_holders",
               "network_entities", "network_evidence"}
    return df.with_columns(
        (_objects(v) if c in objects else pl.Series(v, dtype=df.schema[c])).alias(c)
        for c, v in cols.items()
    )


def regroup_registry_owners(df: pl.DataFrame) -> pl.DataFrame:
    """A registry owner whose building was grouped only by a *different*
    licence holder's name is its own group instead: the popup would
    otherwise say the licence holder "holds" a building the registry says
    someone else owns. A licence naming the owner (any spelling) keeps its
    group; claims networks are never touched."""
    mismatch = pl.Series(
        [
            src == "registry" and net == "licence" and match_key(str(owner)) != match_key(str(lic))
            for src, net, owner, lic in zip(
                df["owner_source"], df["network_source"], df["owner_name"], df["licence_holder"]
            )
        ],
        dtype=pl.Boolean,
    )
    return _where(
        df, pl.lit(mismatch), network_key=pl.col("owner_key"), network_name=pl.col("owner_name"),
        network_source="registry",
    )


def fallback_group_to_owner(df: pl.DataFrame) -> pl.DataFrame:
    """A landlord with no group (no claims cluster, no licence to group by)
    is its own group of one, so the by-ownership-group view never files a
    known landlord under "not on record"."""
    alone = (pl.col("owner_key") != "unknown").fill_null(False) & (
        pl.col("network_key") == "unknown"
    ).fill_null(False)
    return _where(
        df, alone, network_name=pl.col("owner_name"), network_key=pl.col("owner_key"),
        network_source=pl.col("owner_source"),
    )


def _append_overlay_housing(
    conn: sqlite3.Connection, points: pl.DataFrame
) -> pl.DataFrame:
    """Union `overlay_housing` onto the points frame.

    These are SRO/co-op source records that matched no building (see
    ingest/overlay_write.py). They carry coordinates, a name and a housing
    type and little else — no year built, assessed values or owner — so they
    are tagged with a real `source` value rather than being passed off as
    buildings. They have no `units` (an SRO's registered rooms stay in
    sro_registered_rooms, never counted as units). They're excluded from the
    building-only aggregates in reconstruct_filter_config (dataset totals, block/
    neighbourhood unit sums, the units filter histogram) since they remain
    unverified, non-deduplicated points, not confirmed buildings.
    b_id continues from the buildings table's maximum so the two
    sets never collide. Only the points frame's own columns are kept, so
    overlay_housing's internals (overlay_id, source_row_ids, ingested_at) stay
    out of the export. A record that is both co-op and SRO gets
    source=overlay_coop; housing_type still says "co-op, sro".
    """
    flags = [
        pl.col(col).cast(pl.Boolean).fill_null(False)
        for col in ("is_coop", "is_sro", "is_rezoning", "has_vtu_member")
        if col in points.columns
    ]
    overlay = query_frame(conn, "SELECT * FROM overlay_housing")
    if overlay.is_empty():
        return points.with_columns(flags)

    first_id = int(points["b_id"].max()) + 1 if points.height else 1
    n = overlay.height
    overlay = overlay.with_columns(
        b_id=pl.int_range(first_id, first_id + n, dtype=pl.Int64),
        source=pl.when(pl.col("is_coop").cast(pl.Boolean))
        .then(pl.lit("overlay_coop"))
        .otherwise(pl.lit("overlay_sro")),
        owner_name=pl.lit("(Unknown)"),
        owner_key=pl.lit("unknown"),
        licence_holder=pl.lit("(Unknown)"),
        network_key=pl.lit("unknown"),
        network_name=pl.lit("(Unknown)"),
        registered_owners=_objects([] for _ in range(n)),
        registry_pids=_objects([] for _ in range(n)),
        registry_owner_pids=_objects([] for _ in range(n)),
        interest_holders=_objects([] for _ in range(n)),
        member_count=pl.lit(0),
        member_count_all=pl.lit(0),
        has_vtu_member=pl.lit(False),
        member_share_building=pl.lit(0.0),
        members_payload=_objects([] for _ in range(n)),
    )
    # Only the points frame's own columns, in its order; the rest stay null.
    overlay = overlay.select([c for c in points.columns if c in overlay.columns])
    return pl.concat([points, overlay], how="diagonal_relaxed").with_columns(flags)


def resolve_local_area_from_block_numbers(
    blocks_merged: pl.DataFrame, block_numbers_df: pl.DataFrame
) -> pl.Series:
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
    local_area = blocks_merged["local_area"].to_list()
    unknown = [i for i, area in enumerate(local_area) if area == "(Unknown)"]
    if not unknown or block_numbers_df.is_empty():
        return pl.Series("local_area", local_area, dtype=pl.String)

    bn = [
        (geom, area)
        for geom, area in zip(
            (parse_geom(g) for g in block_numbers_df["geom"]), block_numbers_df["geo_local_area"]
        )
        if geom is not None and area is not None
    ]
    if not bn:
        return pl.Series("local_area", local_area, dtype=pl.String)

    block_geoms = blocks_merged["geom_parsed"].to_list()
    block_ids = blocks_merged["block_id"].to_list()
    block_tree = STRtree(block_geoms)

    # Primary: point-in-polygon, one block-numbers point -> one of our blocks.
    matches: dict[int, list[str]] = {}
    for point, area in bn:
        for idx in np.atleast_1d(block_tree.query(point)):
            geom = block_geoms[int(idx)]
            if geom.contains(point) or geom.touches(point):
                matches.setdefault(int(block_ids[int(idx)]), []).append(area)
                break
    resolved_by_block = {bid: _mode(areas) for bid, areas in matches.items()}

    # Fallback: nearest block-numbers point by centroid distance, for blocks
    # that got zero points inside their polygon.
    point_tree = STRtree([geom for geom, _ in bn])
    bn_areas = [area for _, area in bn]
    for i in unknown:
        resolved = resolved_by_block.get(int(block_ids[i]))
        if resolved is None and block_geoms[i] is not None:
            resolved = bn_areas[int(point_tree.nearest(block_geoms[i].centroid))]
        if resolved:
            local_area[i] = resolved
    return pl.Series("local_area", local_area, dtype=pl.String)


def load_overlay_areas(areas: list[OverlayArea]) -> list[tuple[OverlayArea, list]]:
    """Each configured overlay area with its (name, polygon) features. An
    area whose source file is missing gets no polygons, so its flag is
    all-False rather than failing the export.
    """
    return [
        (area, load_area_features(area.source, area.feature) if Path(area.source).exists() else [])
        for area in areas
    ]


def area_keys(flags: dict[str, pl.Series], height: int) -> pl.Series:
    """The keys of every area flagged True on each row, in config order."""
    if not flags:
        return pl.Series("areas", [[]] * height, dtype=pl.List(pl.String))
    keys = pl.DataFrame(flags).select(
        areas=pl.concat_list(
            pl.when(pl.col(key)).then(pl.lit(key)).otherwise(pl.lit(None, pl.String)) for key in flags
        ).list.drop_nulls()
    )
    return keys["areas"]


def _overlay_feature_collection(loaded: list[tuple[OverlayArea, list]]) -> dict:
    """Every overlay polygon, tagged with its area key and its label: the
    feature's own name (one per Village Plan Area) or else the area's name.
    """
    features = [
        {
            "type": "Feature",
            "geometry": _round_geometry(mapping(geom)),
            "properties": {"area": area.key, "name": label or area.name},
        }
        for area, parts in loaded
        for label, geom in parts
    ]
    return {"type": "FeatureCollection", "features": features}


def flag_points_in_polygons(points_df: pl.DataFrame, polygons: list) -> pl.Series:
    """True where a building's point falls inside (or right on the edge of)
    any of `polygons` — the same STRtree point-in-polygon technique as
    resolve_local_area_from_block_numbers above, used here to flag buildings
    within an overlay area (e.g. Chinatown) rather than to resolve a
    neighbourhood label.
    """
    flags = [False] * points_df.height
    if polygons:
        tree = STRtree(polygons)
        for i, (lat, lon) in enumerate(zip(points_df["lat"], points_df["lon"])):
            if _missing(lat) or _missing(lon):
                continue
            point = Point(lon, lat)
            for gi in np.atleast_1d(tree.query(point)):
                geom = polygons[int(gi)]
                if geom.contains(point) or geom.touches(point):
                    flags[i] = True
                    break
    return pl.Series(flags, dtype=pl.Boolean)


def flag_geoms_intersecting_polygons(geoms: pl.Series, polygons: list) -> pl.Series:
    """True where a block's own polygon overlaps any of `polygons` at all.

    Deliberately derived from the block's own geometry, not from whether any
    of its member buildings are flagged — resolve_local_area_from_block_numbers's
    docstring notes the block<->building join itself has a known accuracy
    bug for a handful of blocks, so inferring a boundary flag from building
    membership would inherit that; testing the block polygon directly avoids
    it and keeps the block layer consistent with the buildings drawn on it.
    """
    flags = [False] * len(geoms)
    if polygons:
        tree = STRtree(polygons)
        for i, geom in enumerate(geoms.to_list()):
            if geom is None:
                continue
            for gi in np.atleast_1d(tree.query(geom)):
                if polygons[int(gi)].intersects(geom):
                    flags[i] = True
                    break
    return pl.Series(flags, dtype=pl.Boolean)


def assign_block_labels(blocks_merged: pl.DataFrame) -> pl.Series:
    """Fork of the retired src/sica_mapping/data/spatial.py::assign_block_labels — see its
    docstring. Human-readable "{local_area}-{NN}" labels, reading-order
    (north-to-south, west-to-east) within each neighbourhood. Display-only;
    block_id remains the join/index key everywhere else.
    """
    by_area: dict[str, list[tuple[int, float | None, float | None]]] = {}
    for i, (area, geom) in enumerate(zip(blocks_merged["local_area"], blocks_merged["geom_parsed"])):
        if area is None:
            continue
        c = geom.centroid if geom is not None else None
        by_area.setdefault(area, []).append((i, c.y if c else None, c.x if c else None))
    labels: list[str | None] = [None] * blocks_merged.height
    for area, group in by_area.items():
        # North to south, then west to east; a block without a centroid last.
        ordered = sorted(
            group, key=lambda t: (t[1] is None, -(t[1] or 0.0), t[2] is None, t[2] or 0.0)
        )
        for ordinal, (i, _, _) in enumerate(ordered, start=1):
            labels[i] = f"{area}-{ordinal:02d}"
    return pl.Series("block_label", labels, dtype=pl.String)


def reconstruct_blocks(conn: sqlite3.Connection, points_df: pl.DataFrame) -> pl.DataFrame:
    # Not bbox-filtered: buildings.csv is already city-wide (not West-End-scoped —
    # see merge.py's notes), so restricting blocks to the static config bbox left
    # most of the actual data — the whole eastside and south of the city — with no
    # block polygons at all.
    blocks_raw = query_frame(conn, "SELECT block_id, geom FROM blocks").with_columns(
        pl.col("block_id").cast(pl.Int64), pl.col("geom").cast(pl.String)
    )
    agg = (
        points_df.filter(pl.col("block_id").is_not_null())
        .group_by("block_id")
        .agg(
            buildings=pl.col("address").count(),
            total_units=pl.col("units").sum(),
            median_year_built=pl.col("year_built").median(),
            member_buildings=pl.col("has_vtu_member").sum(),
            total_members=pl.col("member_count").sum(),
            # Most common; ties to the alphabetically first (pandas' mode().iloc[0]).
            local_area=pl.col("local_area").drop_nulls().mode().min(),
        )
        .with_columns(pl.col("block_id").cast(pl.Int64))
    )
    merged = blocks_raw.join(agg, on="block_id", how="left", maintain_order="left").with_columns(
        pl.col("buildings", "total_units", "member_buildings", "total_members").fill_null(0),
        pl.col("local_area").fill_null("(Unknown)"),
    )
    merged = merged.with_columns(
        member_share=pl.when(pl.col("buildings") > 0)
        .then(pl.col("member_buildings") / pl.col("buildings"))
        .otherwise(0.0),
        geom_parsed=_objects(parse_geom(g) for g in merged["geom"]),
    )
    block_numbers_df = query_frame(conn, "SELECT geom, geo_local_area FROM raw_block_numbers")
    merged = merged.with_columns(
        local_area=resolve_local_area_from_block_numbers(merged, block_numbers_df)
    )
    # keep `geom` (GeoJSON text) — callers that need shapely use geom_parsed
    return merged.with_columns(block_label=assign_block_labels(merged))


def reconstruct_filter_config(
    conn: sqlite3.Connection,
    points_df: pl.DataFrame,
    blocks_df: pl.DataFrame,
    now: datetime,
    overlay_areas: list[OverlayArea] = (),
) -> dict[str, object]:
    cfg: dict[str, object] = {}

    pts = points_df.with_columns(
        pl.col("local_area").fill_null("(Unknown)"), pl.col("units").fill_null(0)
    )

    # Building-describing aggregates (neighbourhood counts/units, dataset
    # totals, building_metrics) must exclude overlay_housing rows (source
    # overlay_sro/overlay_coop) — they're SRO/co-op records with no units,
    # value or membership data, not buildings; counting them here would
    # inflate the map's "Buildings" stat (see _append_overlay_housing).
    # bounds stays over every mapped point below since overlay rows are
    # still drawn on the map.
    buildings_only = (
        pts.filter(pl.col("source") == "building") if "source" in pts.columns else pts
    )

    # Most buildings first; equal counts in order of first appearance.
    neighbourhoods = (
        buildings_only.group_by("local_area", maintain_order=True)
        .agg(count=pl.len(), units=pl.col("units").sum())
        .sort("count", descending=True, maintain_order=True)
    )
    cfg["neighbourhoods"] = [
        {"name": area, "count": int(count), "units": int(round(units))}
        for area, count, units in neighbourhoods.iter_rows()
    ]

    # Overlay areas (Chinatown, DEOD, Villages Plan): rendered as more
    # Filters > Neighbourhoods entries after a separator (see legend.ts), not
    # folded into cfg["neighbourhoods"] above since they're boundary overlays
    # a building can belong to *in addition to* its real local_area, not an
    # alternative value of it.
    def _special_area(area: OverlayArea) -> dict:
        flagged = (
            buildings_only.filter(pl.col("areas").list.contains(area.key))
            if "areas" in buildings_only.columns
            else buildings_only.clear()
        )
        return {
            "key": area.key,
            "name": area.name,
            "count": flagged.height,
            "units": int(round(flagged["units"].sum())) if flagged.height else 0,
        }

    cfg["special_areas"] = [_special_area(area) for area in overlay_areas]

    valid_coords = pts.drop_nulls(["lat", "lon"])
    bounds = None
    if not valid_coords.is_empty():
        lat, lon = valid_coords["lat"].to_numpy(), valid_coords["lon"].to_numpy()
        bounds = {
            "lat_min": float(lat.min()),
            "lat_max": float(lat.max()),
            "lon_min": float(lon.min()),
            "lon_max": float(lon.max()),
            # numpy's mean, as pandas computed it: a different summation
            # order shifts the last digit.
            "center_lat": float(np.mean(lat)),
            "center_lon": float(np.mean(lon)),
        }
    cfg["bounds"] = bounds
    cfg["dataset_totals"] = {
        "buildings": buildings_only.height,
        "units": int(buildings_only["units"].sum()),
    }

    building_metrics = build_building_metrics(buildings_only)
    cfg["building_metrics"] = building_metrics
    cfg["building_metric_order"] = [
        key for key in BUILDING_METRICS if key in building_metrics
    ]

    cfg["blocks_total_units_max"] = (
        int(blocks_df["total_units"].max()) if not blocks_df.is_empty() else 0
    )
    cfg["licence_year"] = _licence_year(conn)
    return cfg


def _licence_year(conn: sqlite3.Connection) -> int | None:
    """Business-licence data year of this build (raw_buildings.bsns_year)."""
    row = conn.execute("SELECT MAX(bsns_year) FROM raw_buildings").fetchone()
    return int(row[0]) if row and row[0] is not None else None


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


# ~20 cm. The City's block outlines carry a vertex every few metres along
# straight edges; dropping the ones within this distance of the line removes
# ~80% of them (blocks.geojson 1.44 -> 0.33 MB gzipped) with no visible change.
BLOCK_SIMPLIFY_TOLERANCE = 2e-6


def _simplify_geometry(geom: dict) -> dict:
    simplified = shape(geom).simplify(BLOCK_SIMPLIFY_TOLERANCE, preserve_topology=True)
    return geom if simplified.is_empty else json.loads(json.dumps(mapping(simplified)))


def _round_coord(value) -> float | None:
    return None if _missing(value) else round(float(value), COORD_DECIMALS)


def export_artifacts(
    conn: sqlite3.Connection,
    out_dir: str | Path,
    pid_address_map_path: str | None = None,
    boundary_geojson_path: str | None = None,
    overlay_areas: list[OverlayArea] = (),
    now: datetime | None = None,
    property_managers_path: str | None = None,
) -> None:
    """Write the complete frontend artifact set.

    This is the one-directional contract: every value the map displays is
    produced here. Each file carries a schema_version so a frontend built
    against an older shape fails loudly instead of rendering an empty map.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    points_df = reconstruct_points(
        conn, now, pid_address_map_path,
        load_property_managers(property_managers_path) | managers_from_claims(conn),
        load_listing_aliases(property_managers_path),
    )

    # Overlay areas (Chinatown, DEOD, Villages Plan) double as filterable
    # "special areas" (Filters > Neighbourhoods, after the separator)
    # alongside local_area — a building/block can be in a real neighbourhood
    # *and* any of these at once, so each row carries the list of areas it's
    # in rather than having them folded into local_area.
    loaded_areas = load_overlay_areas(list(overlay_areas))
    polygons = {area.key: [geom for _, geom in parts] for area, parts in loaded_areas}
    points_df = points_df.with_columns(
        areas=area_keys(
            {k: flag_points_in_polygons(points_df, polys) for k, polys in polygons.items()}, points_df.height
        )
    )

    blocks_df = reconstruct_blocks(conn, points_df)
    blocks_df = blocks_df.with_columns(
        areas=area_keys(
            {k: flag_geoms_intersecting_polygons(blocks_df["geom_parsed"], polys) for k, polys in polygons.items()},
            blocks_df.height,
        )
    )

    filter_cfg = reconstruct_filter_config(conn, points_df, blocks_df, now, list(overlay_areas))
    building_payload, network_payload, median_share = _contract_records(conn, points_df)
    filter_cfg["land_share_median"] = median_share

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
    _write_json(out_dir / "building_records.json", building_payload)
    _write_json(out_dir / "networks.json", network_payload)
    _write_json(out_dir / "blocks.geojson", _blocks_feature_collection(blocks_df))

    if boundary_geojson_path:
        shutil.copyfile(
            boundary_geojson_path, out_dir / "local-area-boundary.geojson"
        )

    _write_json(out_dir / "overlay_areas.geojson", _overlay_feature_collection(loaded_areas))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def _blocks_feature_collection(blocks_df: pl.DataFrame) -> dict:
    """Emit the stored GeoJSON geometry, simplified and rounded."""
    property_cols = [
        "block_id",
        "buildings",
        "total_units",
        "median_year_built",
        "local_area",
        "block_label",
        "areas",
    ]
    property_cols = [col for col in property_cols if col in blocks_df.columns]
    features = []
    for row in blocks_df.select("geom", *property_cols).iter_rows(named=True):
        geom = row["geom"]
        if geom is None:
            continue
        if isinstance(geom, str):
            geom = json.loads(geom)
        properties = {col: (None if _missing(row[col]) else row[col]) for col in property_cols}
        features.append(
            {
                "type": "Feature",
                "geometry": _round_geometry(_simplify_geometry(geom)),
                "properties": properties,
            }
        )
    return {
        "type": "FeatureCollection",
        "schema_version": SCHEMA_VERSION,
        "features": features,
    }


def _marker_records(points_df: pl.DataFrame) -> list[dict]:
    """Per-building marker data, including coordinates.

    Styling (radius, colours, rings) is presentation and is computed by the
    frontend (frontend/src/markers.ts); these records carry only data.
    """
    as_int = lambda v: None if _missing(v) else int(v)
    # Not on record is null, as in the contract files (spec 2026-10-08 §5).
    key = lambda v: None if _missing(v) or v == "unknown" else v
    text = lambda v: None if _missing(v) or not str(v).strip() else v
    records = []
    for r in points_df.iter_rows(named=True):
        records.append(
            {
                "b_id": int(r["b_id"]),
                "lat": _round_coord(r["lat"]),
                "lon": _round_coord(r["lon"]),
                "owner_key": key(r.get("owner_key")),
                "network_key": key(r.get("network_key")),
                "block_id": as_int(r.get("block_id")),
                "units": as_int(r.get("units")),
                "year_built": as_int(r.get("year_built")),
                "local_area": text(r.get("local_area")),
                "housing_type": r.get("housing_type") or "",
                "n_issues": as_int(r.get("n_issues")),
                "source": r.get("source", "building"),
            }
        )
    return records


def _contract_records(
    conn: sqlite3.Connection, points_df: pl.DataFrame
) -> tuple[dict, dict, float | None]:
    """building_records.json and networks.json payloads, validated against
    the public contract (tc_core/contract.py — a validation error fails the
    export), plus the city's median land share. The contract models are the
    allowlist: VTU membership data, lineage internals and claim notes on
    points_df have no field to land in (spec 2026-10-08)."""
    rows = list(points_df.iter_rows(named=True))
    shares = LandShares(
        [s for s in (land_share(r) for r in rows if r.get("source") == "building") if s is not None]
    )
    clusters = resolve_entity_clusters(conn)
    buildings = BuildingRecordsFile(
        schema_version=SCHEMA_VERSION,
        records={
            str(int(r["b_id"])): build_building(r, shares=shares, clusters=clusters) for r in rows
        },
    )
    nets = NetworksFile(
        schema_version=SCHEMA_VERSION,
        networks=build_networks(rows, clusters=clusters, kinds=entity_kinds(conn)),
    )
    return buildings.model_dump(mode="json"), nets.model_dump(mode="json"), shares.median
