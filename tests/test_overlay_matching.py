import json
import sqlite3

import polars as pl

from tc_core.db import init_db
from tc_core.ingest.overlays import match_overlays


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


def _buildings():
    return pl.DataFrame(
        {
            "addr_key": ["100 main st"],
            "address": ["100 main st"],
            "lat": [49.28],
            "lon": [-123.1],
            "local_area": ["Downtown"],
        }
    )


def test_matched_sro_sets_flag_on_the_building(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_sro (address, owner, operator, ownership_group, "
        "occupancy_status, registered_rooms, latitude, longitude, ingested_at) "
        "VALUES ('100 Main Street', 'Owner Co', 'Op Co', 'Holding Group', 'Open', "
        "42, 49.28, -123.1, 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert result.unmatched == []
    row = result.matched.row(0, named=True)
    assert bool(row["is_sro"]) is True
    assert row["sro_owner"] == "Owner Co"
    # These two travel through loader columns whose names differ from the
    # table's; a mismatch blanks them silently, so assert them explicitly.
    assert row["sro_registered_rooms"] == "42"
    assert row["sro_ownership_group"] == "Holding Group"


def test_unmatched_coop_becomes_an_unmatched_record(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
        "VALUES ('Elm Co-op', '999 Nowhere Rd', 49.3, -123.15, 'Active', 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert len(result.unmatched) == 1
    rec = result.unmatched[0]
    assert rec["is_coop"] is True
    assert rec["housing_name"] == "Elm Co-op"
    assert rec["lat"] == 49.3


def test_matched_sro_leaves_a_null_unit_count_null(tmp_path):
    # Registered rooms are not dwelling units; they stay in sro_registered_rooms.
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_sro (address, owner, registered_rooms, latitude, longitude, "
        "ingested_at) VALUES ('100 Main Street', 'Owner Co', 42, 49.28, -123.1, 'now')"
    )
    conn.commit()
    buildings = _buildings()
    buildings = buildings.with_columns(units=pl.lit(None, dtype=pl.Int64))

    result = match_overlays(conn, buildings, _boundary(tmp_path))

    assert result.matched.row(0, named=True)["units"] is None
    assert result.matched.row(0, named=True)["sro_registered_rooms"] == "42"


def test_matched_sro_does_not_overwrite_a_reported_unit_count(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_sro (address, owner, registered_rooms, latitude, longitude, "
        "ingested_at) VALUES ('100 Main Street', 'Owner Co', 42, 49.28, -123.1, 'now')"
    )
    conn.commit()
    buildings = _buildings()
    buildings = buildings.with_columns(units=pl.lit(80))

    result = match_overlays(conn, buildings, _boundary(tmp_path))

    assert result.matched.row(0, named=True)["units"] == 80


def test_unmatched_sro_has_no_units_fallback(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_sro (address, owner, registered_rooms, latitude, longitude, "
        "ingested_at) VALUES ('999 Nowhere Rd', 'Owner Co', 60, 49.3, -123.15, 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert len(result.unmatched) == 1
    assert result.unmatched[0].get("units") is None
    assert result.unmatched[0]["sro_registered_rooms"] == "60"


def test_unmatched_coop_has_no_units_fallback(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
        "VALUES ('Elm Co-op', '999 Nowhere Rd', 49.3, -123.15, 'Active', 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert result.unmatched[0].get("units") is None


def test_secondary_address_fallback_matches(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_buildings (address, secondary_addresses, ingested_at) "
        "VALUES ('100 main st', '102 main st', 'now')"
    )
    conn.execute(
        "INSERT INTO raw_sro (address, owner, latitude, longitude, ingested_at) "
        "VALUES ('102 Main Street', 'Owner Co', 49.28, -123.1, 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert result.unmatched == []
    assert bool(result.matched.row(0, named=True)["is_sro"]) is True


def test_record_without_coordinates_is_skipped(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, status, ingested_at) "
        "VALUES ('Ghost Co-op', '999 Nowhere Rd', 'Active', 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert result.unmatched == []


def test_the_first_source_row_wins_when_several_match_one_building(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    for title in ("First Co-op", "Second Co-op"):
        conn.execute(
            "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
            f"VALUES ('{title}', '100 Main St, Vancouver, BC', 49.28, -123.1, 'open', 'now')"
        )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert result.matched.row(0, named=True)["housing_name"] == "First Co-op"
