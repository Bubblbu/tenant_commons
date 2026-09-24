#!/usr/bin/env python3
"""Rebuilds tc_core's SQLite store and exports the frontend artifact set.

Backend only: ingests the sources into SQLite, then writes the artifact
directory (config.toml's `artifacts` path) that frontend/ reads. It renders
nothing — see frontend/README.md for the map.

--skip-ingest  re-export from the existing database without re-ingesting
               (saves ~19s when only export logic changed). Never touches
               the database's tables.

Usage: uv run python scripts/rebuild_data.py [--config config.toml] [--skip-ingest]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tc_core.config import load_ingest_config  # noqa: E402
from tc_core.db import get_connection, init_db  # noqa: E402
from tc_core.export import export_artifacts  # noqa: E402
from tc_core.ingest import run_ingest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(REPO_ROOT / "config.toml"))
    parser.add_argument("--skip-ingest", action="store_true")
    args = parser.parse_args()

    config = load_ingest_config(args.config)
    conn = get_connection(config.db_path)
    if args.skip_ingest:
        print(f"Skipping ingest; exporting from {config.db_path}")
    else:
        print(f"Ingesting into {config.db_path} ...")
        init_db(conn)
        counts = run_ingest(conn, config)
        print(f"Ingest complete: {counts}")

    print(f"Exporting artifacts to {config.artifacts} ...")
    export_artifacts(
        conn,
        config.artifacts,
        pid_address_map_path=config.pid_address_map,
        boundary_geojson_path=config.local_area_boundary_geojson,
        villages_geojson_path=config.villages_plan_areas_geojson,
        chinatown_geojson_path=config.chinatown_boundary_geojson,
    )

    print(f"Done — artifacts in {config.artifacts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
