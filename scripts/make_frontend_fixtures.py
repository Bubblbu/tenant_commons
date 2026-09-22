#!/usr/bin/env python3
"""Generate frontend/fixtures/: a tiny, entirely invented artifact set.

The frontend CI job builds against it (data/ is gitignored, so CI cannot run
ingest). It is produced by the real export_artifacts() from an in-memory
database, so its shape is the real contract, not a hand-written copy. It
proves the build and the contract shape, not the data.

Invented only: no real addresses, owners or membership (vtu_membership stays
empty). Deterministic: fixed timestamps, so regenerating reproduces the
committed bytes — tests/test_frontend_fixtures.py checks that.

Usage: uv run python scripts/make_frontend_fixtures.py [--out frontend/fixtures]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sica_core.db import init_db  # noqa: E402
from sica_core.export import export_artifacts  # noqa: E402

NOW = pd.Timestamp("2026-01-01", tz="UTC")
TS = "2026-01-01T00:00:00+00:00"


def _square(lon: float, lat: float, size: float = 0.002) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[lon, lat], [lon + size, lat], [lon + size, lat + size],
                         [lon, lat + size], [lon, lat]]],
    }


# (id, addr_key, address, area, lat, lon, units, year, land, bldg, ratio,
#  issues, landlord, block, is_coop, is_sro, coop_status, coop_model, coop_url, housing_name)
BUILDINGS = [
    (1, "100 example st", "100 Example St", "Northside", 49.281, -123.129, 40, 1965,
     5000000, 800000, 0.16, 0, 1, 1, 0, 0, None, None, None, None),
    (2, "110 example st", "110 Example St", "Northside", 49.2812, -123.1288, 12, 1978,
     2500000, 400000, 0.16, 1, 1, 1, 1, 0, "Active", "Leasehold", "https://example.org/coop",
     "Example Co-op"),
    (3, "200 sample ave", "200 Sample Ave", "Southside", 49.271, -123.119, 80, 1972,
     9000000, 1500000, 0.17, 0, 2, 2, 0, 1, None, None, None, "Sample Rooms"),
    (4, "210 sample ave", "210 Sample Ave", "Southside", 49.2712, -123.1188, None, None,
     None, None, None, 0, 2, 2, 0, 0, None, None, None, None),
]


def _seed(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO landlords (landlord_id, display_name, owner_key, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [(1, "Example Holdings Ltd", "example-holdings-ltd", TS, TS),
         (2, "Sample Rentals Inc", "sample-rentals-inc", TS, TS)],
    )
    conn.executemany(
        "INSERT INTO blocks (block_id, geom, ingested_at) VALUES (?, ?, ?)",
        [(1, json.dumps(_square(-123.130, 49.280)), TS),
         (2, json.dumps(_square(-123.120, 49.270)), TS),
         (3, json.dumps(_square(-123.110, 49.260)), TS)],  # empty block
    )
    for (bid, key, addr, area, lat, lon, units, year, land, bldg, ratio, issues, landlord,
         block, coop, sro, cstatus, cmodel, curl, hname) in BUILDINGS:
        conn.execute(
            "INSERT INTO buildings (building_id, addr_key, address, local_area, lat, lon, units, "
            "year_built, value_land, value_bldg, bldg_land_ratio, n_issues, landlord_id, block_id, "
            "is_coop, is_sro, coop_status, coop_ownership_model, coop_url, housing_name, sro_owner, "
            "sro_operator, sro_occupancy_status, sro_registered_rooms, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (bid, key, addr, area, lat, lon, units, year, land, bldg, ratio, issues, landlord,
             block, coop, sro, cstatus, cmodel, curl, hname,
             "Sample Owner" if sro else None, "Sample Operator" if sro else None,
             "Open" if sro else None, "24" if sro else None, TS, TS),
        )
    conn.executemany(
        "INSERT INTO overlay_housing (addr_key, address, housing_name, local_area, lat, lon, "
        "is_coop, is_sro, sro_owner, sro_operator, sro_occupancy_status, sro_registered_rooms, "
        "coop_status, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [("300 invented rd", "300 Invented Rd", "Invented Rooms", "Southside", 49.265, -123.105,
          0, 1, "Invented Owner", "Invented Operator", "Open", "10", None, TS),
         ("400 madeup way", "400 Madeup Way", "Madeup Co-op", "Northside", 49.285, -123.135,
          1, 0, None, None, None, None, "Active", TS)],
    )
    conn.commit()


BOUNDARY = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature",
         "properties": {"name": "Northside", "geo_point_2d": {"lon": -123.130, "lat": 49.283}},
         "geometry": _square(-123.140, 49.275, 0.02)},
        {"type": "Feature",
         "properties": {"name": "Southside", "geo_point_2d": {"lon": -123.115, "lat": 49.265}},
         "geometry": _square(-123.125, 49.255, 0.02)},
    ],
}


def build(out_dir: Path) -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)
    with tempfile.TemporaryDirectory() as tmp:
        boundary = Path(tmp) / "local-area-boundary.geojson"
        boundary.write_text(json.dumps(BOUNDARY), encoding="utf-8")
        export_artifacts(conn, out_dir, boundary_geojson_path=str(boundary), now=NOW)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(REPO_ROOT / "frontend" / "fixtures"))
    args = parser.parse_args()
    build(Path(args.out))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
