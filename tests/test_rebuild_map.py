import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from tc_core.db import init_db

REPO_ROOT = Path(__file__).resolve().parent.parent
BLOCK_GEOM = (
    '{"type":"Polygon","coordinates":[[[-123.2,49.2],[-123.2,49.4],'
    '[-123.0,49.4],[-123.0,49.2],[-123.2,49.2]]]}'
)


def _config(tmp_path, db, artifacts, boundary):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[paths]\n"
        'buildings = "unused.csv"\n'
        'addresses = "unused.csv"\n'
        'blocks = "unused.csv"\n'
        'block_numbers = "unused.csv"\n'
        'vtu_raw = "unused.csv"\n'
        f'tc_core_db = "{db}"\n'
        f'artifacts = "{artifacts}"\n'
        f'local_area_boundary_geojson = "{boundary}"\n'
    )
    return cfg


def test_skip_ingest_exports_the_existing_database_untouched(tmp_path):
    db = tmp_path / "tc.db"
    conn = sqlite3.connect(db)
    init_db(conn)
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, "
        "created_at, updated_at) VALUES ('100 main st', '100 Main St', 49.28, "
        "-123.1, 'Downtown', 50, 'now', 'now')"
    )
    conn.execute(
        "INSERT INTO blocks (block_id, geom, ingested_at) VALUES (1, ?, 'now')",
        (BLOCK_GEOM,),
    )
    conn.commit()
    conn.close()
    boundary = tmp_path / "boundary.geojson"
    boundary.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    artifacts = tmp_path / "artifacts"

    result = subprocess.run(
        [sys.executable, "scripts/rebuild_map.py",
         "--config", str(_config(tmp_path, db, artifacts, boundary)), "--skip-ingest"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    markers = json.loads((artifacts / "marker_metadata.json").read_text())["markers"]
    # The seeded row survived: --skip-ingest must not call init_db().
    assert [m["b_id"] for m in markers] == [1]
    assert (artifacts / "local-area-boundary.geojson").exists()
