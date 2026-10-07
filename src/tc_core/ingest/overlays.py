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

Matching is address-key only (`tc_core.normalize.AddressMatcher`), no
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
import math
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Callable

import polars as pl
from shapely.geometry import Point, shape

from ..normalize import AddressMatcher, address_key_variants
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
    matched: pl.DataFrame
    unmatched: list[dict] = field(default_factory=list)


def _missing(val) -> bool:
    return val is None or (isinstance(val, float) and math.isnan(val))


def _clean(val) -> str:
    if _missing(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _clean_expr(col: str) -> pl.Expr:
    """_clean() as an expression: stripped text, "" for missing or "nan"."""
    s = pl.col(col).cast(pl.String).str.strip_chars()
    return pl.when(s.is_null() | (s.str.to_lowercase() == "nan")).then(pl.lit("")).otherwise(s)


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
    if _missing(lat) or _missing(lon):
        return ""
    point = Point(float(lon), float(lat))
    for name, poly in boundary_polys:
        if poly.contains(point):
            return name
    return ""


def _match_key(street: str, matcher: AddressMatcher) -> str:
    """The building key AddressMatcher resolves `street` to; otherwise the
    most-stripped variant, so unmatched records for different units of one
    building end up sharing a key (and one marker).
    """
    return matcher.match(street) or address_key_variants(street)[-1]


def _coop_street(address) -> str:
    return str(address).split(",")[0].strip()


_REZONING_NAME_SPLIT_RE = re.compile(r"\s+and\s+|\s*&\s*|;")


def _rezoning_street(name) -> str:
    s = str(name).split("(")[0]
    return _REZONING_NAME_SPLIT_RE.split(s, maxsplit=1)[0].strip()


def _split_matches(
    source: pl.DataFrame,
    column: str,
    street: Callable[[object], str],
    matcher: AddressMatcher,
    addr_keys: list[str],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Key each source row, then split it into (matched, unmatched) rows.
    Several rows matching one building: the first in source order wins."""
    source = source.with_columns(
        addr_key=pl.col(column).map_elements(
            lambda a: _match_key(street(a), matcher), return_dtype=pl.String, skip_nulls=False
        )
    )
    hit = pl.col("addr_key").is_in(addr_keys)
    matched = source.filter(hit).unique("addr_key", keep="first", maintain_order=True)
    return matched, source.filter(~hit)


def _apply_matches(
    df: pl.DataFrame, matched: pl.DataFrame, flag: str, fields: dict[str, str]
) -> pl.DataFrame:
    """Set `flag` and each source column -> building column in `fields` on
    the buildings `matched` resolved to; other buildings keep their values."""
    fields = {src: dst for src, dst in fields.items() if src in matched.columns}
    lookup = matched.select(
        "addr_key",
        pl.lit(True).alias("_hit"),
        *(_clean_expr(src).alias(f"_{dst}") for src, dst in fields.items()),
    )
    hit = pl.col("_hit").fill_null(False)
    return (
        df.join(lookup, on="addr_key", how="left", maintain_order="left")
        .with_columns(
            pl.when(hit).then(True).otherwise(pl.col(flag)).alias(flag),
            *(
                pl.when(hit).then(pl.col(f"_{dst}")).otherwise(pl.col(dst)).alias(dst)
                for dst in fields.values()
            ),
        )
        .drop("_hit", *(f"_{dst}" for dst in fields.values()))
    )


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
    if _missing(lat) or _missing(lon):
        logger.warning("Skipping unplaceable housing record (no lat/lon): %s", address)
        return
    row = extras.setdefault(
        key, {"addr_key": key, "address": address, "lat": float(lat), "lon": float(lon)}
    )
    row.update(flags)
    if not _missing(source_id):
        row.setdefault("source_row_ids", {}).setdefault(source_table, []).append(
            int(source_id)
        )
    if name and not row.get("housing_name"):
        row["housing_name"] = name


def match_overlays(
    conn: sqlite3.Connection,
    buildings_df: pl.DataFrame,
    boundary_path: str,
) -> OverlayMatchResult:
    addr_keys = buildings_df["addr_key"].unique().to_list()
    boundary_polys = _build_boundary_polys(load_boundary_feature_collection(boundary_path))
    secondary_index = load_secondary_address_index(conn)
    matcher = AddressMatcher(set(addr_keys), aliases=secondary_index)
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
    df = buildings_df.with_columns(
        is_coop=pl.lit(False),
        coop_status=pl.lit(""),
        coop_ownership_model=pl.lit(""),
        coop_url=pl.lit(""),
        housing_name=pl.lit(""),
        is_sro=pl.lit(False),
        sro_owner=pl.lit(""),
        sro_operator=pl.lit(""),
        sro_operator_group=pl.lit(""),
        sro_ownership_group=pl.lit(""),
        sro_occupancy_status=pl.lit(""),
        sro_registered_rooms=pl.lit(""),
        is_rezoning=pl.lit(False),
        rezoning_status=pl.lit(""),
        rezoning_status_group=pl.lit(""),
        rezoning_category=pl.lit(""),
        rezoning_status_detail=pl.lit(""),
        rezoning_link=pl.lit(""),
    )

    # ---- Co-ops ----
    if coops is not None:
        matched, unmatched = _split_matches(coops, "address", _coop_street, matcher, addr_keys)
        logger.info(
            "Co-ops: %d/%d matched an existing building", matched.height, coops.height
        )
        df = _apply_matches(
            df,
            matched,
            "is_coop",
            {
                "status": "coop_status",
                "ownership_model": "coop_ownership_model",
                "read_more_url": "coop_url",
                "title": "housing_name",
            },
        )

        for row in unmatched.iter_rows(named=True):
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
        matched, unmatched = _split_matches(sro, "address", str, matcher, addr_keys)
        logger.info(
            "SRO/SRA: %d/%d matched an existing building", matched.height, sro.height
        )
        # Registered rooms are not dwelling units: they stay in
        # sro_registered_rooms and never fill `units`.
        df = _apply_matches(
            df,
            matched,
            "is_sro",
            {
                "owner": "sro_owner",
                "operator": "sro_operator",
                "operator_group": "sro_operator_group",
                "ownership_group": "sro_ownership_group",
                "occupancy_status": "sro_occupancy_status",
                "#_registered_rooms": "sro_registered_rooms",
            },
        )

        for row in unmatched.iter_rows(named=True):
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
                },
                name=_clean(row.get("building_name")),
                source_table="raw_sro",
                source_id=row.get("raw_sro_id"),
            )

    # ---- Rezoning applications ----
    if rezoning is not None:
        matched, unmatched = _split_matches(
            rezoning.with_row_index("_idx"), "name", _rezoning_street, matcher, addr_keys
        )
        logger.info(
            "Rezoning applications: %d/%d matched an existing building",
            matched.height,
            rezoning.height,
        )
        df = _apply_matches(
            df,
            matched,
            "is_rezoning",
            {
                "status": "rezoning_status",
                "category": "rezoning_category",
                "status_detail": "rezoning_status_detail",
                "link": "rezoning_link",
            },
        ).with_columns(
            rezoning_status_group=pl.when(pl.col("is_rezoning"))
            .then(
                pl.when(pl.col("rezoning_status").str.to_lowercase() == "approved")
                .then(pl.lit("closed"))
                .otherwise(pl.lit("open"))
            )
            .otherwise(pl.col("rezoning_status_group"))
        )

        for row in unmatched.iter_rows(named=True):
            lat, lon = row.get("latitude"), row.get("longitude")
            status = _clean(row.get("status"))
            unmatched_records.append(
                {
                    # rezoning_applications.csv's own ID is NOT reliably
                    # unique per row — e.g. RZ285 covers two entirely
                    # different addresses/lat-lons as separate rows (a
                    # multi-site umbrella application) — confirmed via a
                    # real duplicate-key collision during testing.
                    "synthetic_id": f"rezoning-{row.get('id')}-{row['_idx']}",
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

    df = df.with_columns(
        housing_type=pl.when(pl.col("is_coop") & pl.col("is_sro"))
        .then(pl.lit("co-op, sro"))
        .when(pl.col("is_coop"))
        .then(pl.lit("co-op"))
        .when(pl.col("is_sro"))
        .then(pl.lit("sro"))
        .otherwise(pl.lit(""))
    )

    for rec in extras.values():
        rec["local_area"] = _resolve_local_area(
            rec.get("lat"), rec.get("lon"), boundary_polys
        )

    return OverlayMatchResult(matched=df, unmatched=list(extras.values()))
