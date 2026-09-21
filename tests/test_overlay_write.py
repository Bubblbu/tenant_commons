import json
import sqlite3

from sica_core.db import init_db
from sica_core.ingest.overlay_write import ingest_overlays


def _boundary(tmp_path):
    p = tmp_path / "local-area-boundary.geojson"
    p.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Downtown"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-123.2, 49.2],
                                    [-123.2, 49.4],
                                    [-123.0, 49.4],
                                    [-123.0, 49.2],
                                    [-123.2, 49.2],
                                ]
                            ],
                        },
                    }
                ],
            }
        )
    )
    return str(p)


def _seed_building(conn):
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, "
        "created_at, updated_at) "
        "VALUES ('100 main st', '100 main st', 49.28, -123.1, 'Downtown', 'now', 'now')"
    )


def test_matched_record_sets_flags_on_buildings(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.execute(
        "INSERT INTO raw_sro (address, owner, ownership_group, latitude, longitude, "
        "ingested_at) VALUES ('100 Main Street', 'Owner Co', 'Holding Group', "
        "49.28, -123.1, 'now')"
    )
    conn.commit()

    written = ingest_overlays(conn, _boundary(tmp_path))

    assert written == 0
    row = conn.execute(
        "SELECT is_sro, sro_owner, sro_ownership_group FROM buildings "
        "WHERE addr_key = '100 main st'"
    ).fetchone()
    assert row == (1, "Owner Co", "Holding Group")


def test_unmatched_record_lands_in_overlay_housing(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
        "VALUES ('Elm Co-op', '999 Nowhere Rd', 49.3, -123.15, 'Active', 'now')"
    )
    conn.commit()

    written = ingest_overlays(conn, _boundary(tmp_path))

    assert written == 1
    row = conn.execute(
        "SELECT addr_key, housing_name, is_coop, local_area FROM overlay_housing"
    ).fetchone()
    assert row[1] == "Elm Co-op"
    assert row[2] == 1
    assert row[3] == "Downtown"


def test_buildings_count_is_unaffected_by_unmatched_records(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
        "VALUES ('Elm Co-op', '999 Nowhere Rd', 49.3, -123.15, 'Active', 'now')"
    )
    conn.commit()

    ingest_overlays(conn, _boundary(tmp_path))

    assert conn.execute("SELECT COUNT(*) FROM buildings").fetchone()[0] == 1


def test_rerun_replaces_rather_than_duplicates(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
        "VALUES ('Elm Co-op', '999 Nowhere Rd', 49.3, -123.15, 'Active', 'now')"
    )
    conn.commit()

    ingest_overlays(conn, _boundary(tmp_path))
    ingest_overlays(conn, _boundary(tmp_path))

    assert conn.execute("SELECT COUNT(*) FROM overlay_housing").fetchone()[0] == 1
