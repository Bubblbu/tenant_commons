"""Config loading for tc_core ingest.

Forked from `src/sica_mapping/cli.py`'s `_load_config`/`_merge_config` (retired; see
normalize.py's provenance note) and trimmed to what ingest actually needs:
the same four source CSV paths already used by `config.toml`, plus the
tc_core database path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - only for <3.11
    tomllib = None

DEFAULT_DB_PATH = "data/derived/tc_core.db"
DEFAULT_BBOX = "-123.18,49.265,-123.10,49.295"
DEFAULT_BOUNDARY_GEOJSON = "data/raw/cov_open_data/local-area-boundary.geojson"
DEFAULT_ARTIFACTS_DIR = "data/derived/artifacts"
# "vtu_raw" is the raw NationBuilder export (data/raw/nationbuilder/), allow-
# listed down to a few columns by ingest/membership.py.
_REQUIRED_PATHS = ("buildings", "addresses", "blocks", "block_numbers", "vtu_raw")


@dataclass
class IngestConfig:
    buildings: str
    addresses: str
    blocks: str
    block_numbers: str
    vtu_raw: str
    db_path: str = DEFAULT_DB_PATH
    bbox: tuple[float, float, float, float] = (-123.18, 49.265, -123.10, 49.295)
    # Optional: manually-curated ownership research CSV (see
    # ingest/ownership_claims.py). Not in _REQUIRED_PATHS — unlike the other
    # sources, there may genuinely be no claims yet to import.
    ownership_claims: str | None = None
    # Optional: SRO/SRA, co-op, and rezoning-application overlays (see
    # ingest/raw_sro.py, raw_coops.py, raw_rezoning.py). Same config.toml
    # keys used for these (sro_housing/coops/rezoning_applications) — not
    # required, since a fresh setup may not have these sources configured
    # yet.
    sro_housing: str | None = None
    coops: str | None = None
    rezoning_applications: str | None = None
    # Optional: Samwise's BC Land Owner Transparency Registry export (see
    # ingest/raw_lotr.py, ingest/lotr_claims.py). Not wired into run_ingest —
    # imported standalone via scripts/import_lotr_claims.py, decoupled from
    # the main rebuild cadence.
    lotr_ownership: str | None = None
    # Optional: PID -> addr_key bridge (scripts/export_pid_address_map.py).
    # Used by portfolios.py to join claims-derived landlord clusters onto
    # buildings for the map export; absent it, export_artifacts() just skips
    # portfolio attachment.
    pid_address_map: str | None = None
    # Neighbourhood boundaries, read straight off disk rather than ingested
    # into a table: the fetcher already downloads this GeoJSON (see
    # fetch/cov_open_data.py) and the overlay matcher needs it for the
    # point-in-polygon local_area lookup on records with no building match.
    local_area_boundary_geojson: str = DEFAULT_BOUNDARY_GEOJSON
    # Optional: hand-traced City "Village Plan Area" boundaries (see
    # data/curated/villages_plan_areas.geojson's provenance) for the map's
    # reference overlay. City/program-specific, not part of _REQUIRED_PATHS —
    # a non-Vancouver deployment wouldn't have this.
    villages_plan_areas_geojson: str | None = None
    # Optional: the Chinatown boundary already used by prepare/properties.py
    # (via DataPaths.chinatown_boundary) to flag buildings — reused here,
    # unmodified, as a second map reference overlay.
    chinatown_boundary_geojson: str | None = None
    # Optional: hand-curated list of property-management companies
    # (curated/property_managers.toml). A rental licence they hold names the
    # building's manager, not its landlord (see export.apply_property_managers).
    property_managers: str | None = None
    # Optional: directory of dated property-manager listing snapshots
    # (data/raw/property_managers/<manager>/<YYYY-MM-DD>.json), accumulated
    # into raw_manager_listings (ingest/manager_listings.py).
    manager_listings: str | None = None
    # Where export_artifacts() writes the frontend's input (the artifact
    # directory, spec §3/§6). frontend/ reads it via TC_ARTIFACTS_DIR.
    artifacts: str = DEFAULT_ARTIFACTS_DIR


def _load_raw(path: str) -> dict[str, object]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    suffix = config_path.suffix.lower()
    if suffix in {".toml", ".tml"}:
        if tomllib is None:
            raise RuntimeError(
                "tomllib not available; upgrade to Python 3.11+ or use JSON config."
            )
        return tomllib.loads(config_path.read_text())
    if suffix == ".json":
        return json.loads(config_path.read_text())
    raise ValueError(f"Unsupported config format: {config_path.suffix}")


def load_ingest_config(path: str) -> IngestConfig:
    raw = _load_raw(path)
    flat: dict[str, object] = dict(raw)
    for key in ("paths", "options"):
        section = raw.get(key)
        if isinstance(section, dict):
            flat.update(section)

    missing = [field for field in _REQUIRED_PATHS if field not in flat]
    if missing:
        raise ValueError(f"config missing required paths: {', '.join(missing)}")

    bbox_str = str(flat.get("bbox", DEFAULT_BBOX))
    bbox = tuple(float(v) for v in bbox_str.split(","))

    return IngestConfig(
        buildings=str(flat["buildings"]),
        addresses=str(flat["addresses"]),
        blocks=str(flat["blocks"]),
        block_numbers=str(flat["block_numbers"]),
        vtu_raw=str(flat["vtu_raw"]),
        db_path=str(flat.get("tc_core_db", DEFAULT_DB_PATH)),
        bbox=bbox,
        ownership_claims=(
            str(flat["ownership_claims"]) if flat.get("ownership_claims") else None
        ),
        sro_housing=str(flat["sro_housing"]) if flat.get("sro_housing") else None,
        coops=str(flat["coops"]) if flat.get("coops") else None,
        rezoning_applications=(
            str(flat["rezoning_applications"]) if flat.get("rezoning_applications") else None
        ),
        lotr_ownership=(
            str(flat["lotr_ownership"]) if flat.get("lotr_ownership") else None
        ),
        pid_address_map=(
            str(flat["pid_address_map"]) if flat.get("pid_address_map") else None
        ),
        local_area_boundary_geojson=str(
            flat.get("local_area_boundary_geojson", DEFAULT_BOUNDARY_GEOJSON)
        ),
        villages_plan_areas_geojson=(
            str(flat["villages_plan_areas_geojson"])
            if flat.get("villages_plan_areas_geojson")
            else None
        ),
        chinatown_boundary_geojson=(
            str(flat["chinatown_boundary_geojson"])
            if flat.get("chinatown_boundary_geojson")
            else None
        ),
        property_managers=(
            str(flat["property_managers"]) if flat.get("property_managers") else None
        ),
        manager_listings=(
            str(flat["manager_listings"]) if flat.get("manager_listings") else None
        ),
        artifacts=str(flat.get("artifacts", DEFAULT_ARTIFACTS_DIR)),
    )
