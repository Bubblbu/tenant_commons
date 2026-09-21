#!/usr/bin/env python3
"""Rebuilds sica_core's SQLite store and exports the frontend artifact set.

Backend only: ingests the sources into SQLite, then writes the artifact
directory (config.toml's `artifacts` path) that frontend/ reads. It renders
nothing — see frontend/README.md for the map.

--skip-ingest  re-export from the existing database without re-ingesting
               (saves ~19s when only export logic changed). Never touches
               the database's tables.
--folium       additionally render the legacy Folium map into www/, as the
               parity reference for the Vite build. Temporary: removed with
               sica_mapping.

Usage: uv run python scripts/rebuild_map.py [--config config.toml] [--skip-ingest] [--folium]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sica_core.config import load_ingest_config  # noqa: E402
from sica_core.db import get_connection, init_db  # noqa: E402
from sica_core.export import export_artifacts, export_to_cache  # noqa: E402
from sica_core.ingest import run_ingest  # noqa: E402

# Only used by --folium: sica_mapping.cli.DEFAULT_DATA_DIR.
LEGACY_CACHE_DIR = REPO_ROOT / ".preprocessed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(REPO_ROOT / "config.toml"))
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--folium", action="store_true")
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
    )

    if args.folium:
        print("Rendering the legacy Folium map (parity reference) ...")
        export_to_cache(conn, LEGACY_CACHE_DIR, pid_address_map_path=config.pid_address_map)
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "build_sica_map.py"),
                "--config", args.config,
                "--stage", "frontend",
                "--data-dir", str(LEGACY_CACHE_DIR),
            ],
            cwd=REPO_ROOT,
            check=True,
        )
        print("Legacy map: www/index.html")

    print(f"Done — artifacts in {config.artifacts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
