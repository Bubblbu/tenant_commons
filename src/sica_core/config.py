"""Config loading for sica_core ingest.

Forked from `src/sica_mapping/cli.py`'s `_load_config`/`_merge_config` (see
normalize.py's provenance note) and trimmed to what ingest actually needs:
the same four source CSV paths already used by `config.toml`, plus the
sica_core database path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - only for <3.11
    tomllib = None

DEFAULT_DB_PATH = "data/sica_core.db"
DEFAULT_BBOX = "-123.18,49.265,-123.10,49.295"
# "vtu_raw", not "vtu" — config.toml's "vtu" key is sica_mapping's public,
# address-aggregated extract (data/vtu_membership_public.csv). sica_core's
# ingest needs the raw, un-anonymized NationBuilder export instead (allow-
# listed down to a few columns by ingest/membership.py); giving it its own
# key avoids the two builds silently fighting over one config value.
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
    # keys sica_mapping already uses for these (sro_housing/coops/
    # rezoning_applications) — not required, since a fresh setup may not
    # have these sources configured yet.
    sro_housing: str | None = None
    coops: str | None = None
    rezoning_applications: str | None = None
    # Optional: Samwise's BC Land Owner Transparency Registry export (see
    # ingest/raw_lotr.py, ingest/lotr_claims.py). Not wired into run_ingest —
    # imported standalone via scripts/import_lotr_claims.py, decoupled from
    # the main rebuild cadence.
    lotr_ownership: str | None = None


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
        db_path=str(flat.get("sica_core_db", DEFAULT_DB_PATH)),
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
    )
