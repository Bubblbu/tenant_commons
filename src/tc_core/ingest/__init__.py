"""Ingest orchestration: CSVs -> tc_core SQLite tables.

Order matters for FK dependencies: raw tables first, then the merge step
(which needs both raw_buildings and raw_addresses), then overlays (matches raw_sro/raw_coops/
raw_rezoning against the merged buildings: flags matched buildings, writes
the rest to overlay_housing; needs the local-area boundary GeoJSON), then
ownership_claims last (independent of everything else, but kept at the end
since it's the one optional/persistent source).

raw_sro/raw_coops/raw_rezoning themselves are raw storage (see raw_sro.py's
docstring), so their position among the raw tables is arbitrary; grouped
with the other raw ingests for readability. All three are optional, same as
ownership_claims, since a fresh setup may not have them configured; the
overlays step runs regardless and matches whatever is present.

Each stage's inserts are already scoped in their own transaction. If a stage
fails partway, nothing is silently left half-correct: every REBUILDABLE table
gets dropped and recreated by `init_db()` at the start of the next run, so
recovery is just "call init_db() again, then re-run ingest" — no rollback
machinery needed. `ownership_claims` is never dropped by ingest, and its own
CSV importer is upsert-safe to re-run (see ingest/ownership_claims.py), so
it isn't at risk either way.

Every source call is wrapped by `run_source`, which records a row in
`ingest_runs` (success or failure, with a full traceback on failure) before
letting a failure keep propagating — this preserves the fail-fast behaviour
above exactly, it just adds a persistent record of what happened. See
ingest/tracking.py.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import traceback
from datetime import datetime, timezone
from typing import Any, Callable

from ..config import IngestConfig, load_ingest_config
from ..db import get_connection, init_db
from .block_numbers import ingest_raw_block_numbers
from .blocks import ingest_raw_blocks
from .building_names import derive_building_names
from .manager_listings import ingest_manager_listings
from .merge import run_merge
from .overlay_write import ingest_overlays
from .ownership_claims import ingest_ownership_claims
from .raw_addresses import ingest_raw_addresses
from .raw_buildings import ingest_raw_buildings
from .raw_city_owned import ingest_raw_city_owned
from .raw_housing_sources import ingest_raw_licences_2024, ingest_raw_non_market
from .raw_coops import ingest_raw_coops
from .raw_rezoning import ingest_raw_rezoning
from .raw_sro import ingest_raw_sro
from .strata_lot_pids import ingest_strata_lot_pids
from .tracking import new_run_id, record_run

logger = logging.getLogger("tc_core.ingest")


def run_source(
    conn: sqlite3.Connection,
    run_id: str,
    source_name: str,
    fn: Callable[..., int],
    *args: Any,
) -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        count = fn(*args)
    except Exception:
        record_run(
            conn, run_id, source_name,
            started_at=started_at, status="failure",
            error_message=traceback.format_exc(),
        )
        raise
    record_run(
        conn, run_id, source_name,
        started_at=started_at, status="success", row_count=count,
    )
    logger.info("%s: %d rows", source_name, count)
    return count


def run_ingest(conn: sqlite3.Connection, config: IngestConfig) -> dict[str, int]:
    run_id = new_run_id()
    counts: dict[str, int] = {}
    counts["raw_buildings"] = run_source(
        conn, run_id, "raw_buildings", ingest_raw_buildings, conn, config.buildings
    )
    counts["raw_addresses"] = run_source(
        conn, run_id, "raw_addresses", ingest_raw_addresses, conn, config.addresses
    )
    counts["raw_blocks"] = run_source(
        conn, run_id, "raw_blocks", ingest_raw_blocks, conn, config.blocks
    )
    counts["raw_block_numbers"] = run_source(
        conn, run_id, "raw_block_numbers", ingest_raw_block_numbers, conn, config.block_numbers
    )
    # SRO/co-op/rezoning raw storage: no FK, optional since a fresh setup may
    # not have these sources configured yet. Matched against buildings by the
    # overlays step after the merge.
    if config.sro_housing:
        counts["raw_sro"] = run_source(
            conn, run_id, "raw_sro", ingest_raw_sro, conn, config.sro_housing
        )
    if config.coops:
        counts["raw_coops"] = run_source(
            conn, run_id, "raw_coops", ingest_raw_coops, conn, config.coops
        )
    if config.rezoning_applications:
        counts["raw_rezoning"] = run_source(
            conn, run_id, "raw_rezoning", ingest_raw_rezoning, conn, config.rezoning_applications
        )
    if config.city_owned_properties:
        counts["raw_city_owned_properties"] = run_source(
            conn, run_id, "raw_city_owned_properties", ingest_raw_city_owned, conn,
            config.city_owned_properties,
        )
    if config.licences_2024:
        counts["raw_licences_2024"] = run_source(
            conn, run_id, "raw_licences_2024", ingest_raw_licences_2024, conn, config.licences_2024
        )
    if config.non_market_housing:
        counts["raw_non_market"] = run_source(
            conn, run_id, "raw_non_market", ingest_raw_non_market, conn, config.non_market_housing
        )
    # Raw inputs the merge reads: listings add buildings (ingest/listing_buildings.py).
    if config.manager_listings:
        counts["raw_manager_listings"] = run_source(
            conn, run_id, "raw_manager_listings", ingest_manager_listings, conn, config.manager_listings
        )
    if config.strata_lot_pids:
        counts["strata_lot_pids"] = run_source(
            conn, run_id, "strata_lot_pids", ingest_strata_lot_pids, conn, config.strata_lot_pids
        )
    counts["buildings"] = run_source(conn, run_id, "buildings", run_merge, conn)
    counts["overlays"] = run_source(
        conn, run_id, "overlays", ingest_overlays, conn,
        config.local_area_boundary_geojson,
    )
    counts["building_names"] = run_source(
        conn, run_id, "building_names", derive_building_names, conn
    )
    if config.ownership_claims:
        counts["ownership_claims"] = run_source(
            conn, run_id, "ownership_claims", ingest_ownership_claims, conn, config.ownership_claims
        )
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Ingest CSVs into tc_core's SQLite store")
    parser.add_argument("--config", required=True, help="TOML/JSON config with source paths")
    args = parser.parse_args()

    config = load_ingest_config(args.config)
    conn = get_connection(config.db_path)
    init_db(conn)
    counts = run_ingest(conn, config)
    summary = ", ".join(f"{name}={count}" for name, count in counts.items())
    logger.info("Ingest complete: %s", summary)


if __name__ == "__main__":
    main()
