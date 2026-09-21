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


def test_overlay_housing_records_its_source_rows(tmp_path):
    """CLAUDE.md §3 lineage hook: a co-op and an SRO at the same unmatched
    address merge into one row, which keeps both source ids, per table."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.execute(
        "INSERT INTO raw_coops (raw_coop_id, title, address, lat, lon, status, ingested_at) "
        "VALUES (7, 'Elm Co-op', '999 Nowhere Rd, Vancouver, BC', 49.3, -123.15, 'Active', 'now')"
    )
    conn.execute(
        "INSERT INTO raw_sro (raw_sro_id, address, owner, latitude, longitude, ingested_at) "
        "VALUES (3, '999 Nowhere Rd', 'Owner Co', 49.3, -123.15, 'now')"
    )
    conn.commit()

    assert ingest_overlays(conn, _boundary(tmp_path)) == 1

    (lineage,) = conn.execute("SELECT source_row_ids FROM overlay_housing").fetchone()
    assert json.loads(lineage) == {"raw_coops": [7], "raw_sro": [3]}


def test_building_overlay_columns_match_what_the_matcher_produces(tmp_path):
    """The 18 columns are listed once, in BUILDING_OVERLAY_COLUMNS; the matcher
    and the buildings schema must agree with it, or matcher output is lost."""
    from sica_core.ingest.overlay_write import BUILDING_OVERLAY_COLUMNS
    from sica_core.ingest.overlays import match_overlays
    import pandas as pd

    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.commit()
    buildings = pd.read_sql_query(
        "SELECT building_id, addr_key, address, lat, lon, local_area FROM buildings", conn
    )

    added = set(match_overlays(conn, buildings, _boundary(tmp_path)).matched.columns)
    added -= set(buildings.columns) | {"housing_type"}
    schema_cols = {r[1] for r in conn.execute("PRAGMA table_info(buildings)")}

    assert added == set(BUILDING_OVERLAY_COLUMNS)
    assert set(BUILDING_OVERLAY_COLUMNS) <= schema_cols
