import json
import sqlite3

from tc_core.db import init_db
from tc_core.ingest.overlay_sources import (
    load_boundary_feature_collection,
    load_coops_frame,
    load_rezoning_frame,
    load_secondary_address_index,
    load_sro_frame,
)


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def test_returns_none_when_table_empty():
    conn = _conn()
    assert load_sro_frame(conn) is None
    assert load_coops_frame(conn) is None
    assert load_rezoning_frame(conn) is None


def test_loads_sro_rows():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_sro (address, building_name, owner, operator, "
        "occupancy_status, registered_rooms, latitude, longitude, ingested_at) "
        "VALUES ('100 main st', 'Main Rooms', 'Owner Co', 'Op Co', 'Open', 42, "
        "49.28, -123.1, 'now')"
    )
    conn.commit()
    df = load_sro_frame(conn)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["address"] == "100 main st"
    assert row["owner"] == "Owner Co"
    # Returned under the matcher body's name, not the table's — see Interfaces.
    assert row["#_registered_rooms"] == 42
    assert "registered_rooms" not in df.columns
    assert {"operator_group", "ownership_group", "raw_sro_id"} <= set(df.columns)


def test_loads_coop_rows():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, "
        "ownership_model, website, ingested_at) "
        "VALUES ('Elm Co-op', '300 elm st', 49.3, -123.2, 'Active', "
        "'Leasehold', 'https://example.org', 'now')"
    )
    conn.commit()
    df = load_coops_frame(conn)
    assert len(df) == 1
    assert df.iloc[0]["title"] == "Elm Co-op"
    assert "raw_coop_id" in df.columns


def test_loads_rezoning_rows_with_id_alias():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_rezoning (source_id, name, status, ingested_at) "
        "VALUES ('RZ285', 'Downtown Mixed-Use', 'Approved', 'now')"
    )
    conn.commit()
    df = load_rezoning_frame(conn)
    assert len(df) == 1
    row = df.iloc[0]
    # Returned under the matcher body's name, not the table's source_id
    assert row["id"] == "RZ285"
    assert "source_id" in df.columns  # source_id is still there from SELECT *
    assert row["name"] == "Downtown Mixed-Use"


def test_secondary_address_index_maps_to_primary_addr_key():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_buildings (address, secondary_addresses, ingested_at) "
        "VALUES ('100 main st', '102 main st; 104 main st', 'now')"
    )
    conn.commit()
    idx = load_secondary_address_index(conn)
    assert idx["102 main st"] == "100 main st"
    assert idx["104 main st"] == "100 main st"


def test_secondary_address_index_normalizes_like_the_matcher():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_buildings (address, secondary_addresses, ingested_at) "
        "VALUES ('100 Main Street', '102 Main Street, rear; 104 Main Avenue', 'now')"
    )
    conn.commit()
    idx = load_secondary_address_index(conn)
    # Keys go through addr_key_from_freeform, not plain lowercasing:
    # "Street" -> "st", "Avenue" -> "ave".
    assert idx["104 main ave"] == "100 main st"
    # Split on ";" only — a comma inside one entry does not split it.
    assert idx["102 main st, rear"] == "100 main st"
    assert len(idx) == 2


def test_secondary_address_index_ignores_blank_values():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_buildings (address, secondary_addresses, ingested_at) "
        "VALUES ('100 main st', '', 'now')"
    )
    conn.commit()
    assert load_secondary_address_index(conn) == {}


def test_boundary_feature_collection_reads_geojson(tmp_path):
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
                            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                        },
                    }
                ],
            }
        )
    )
    fc = load_boundary_feature_collection(str(p))
    assert fc["features"][0]["properties"]["name"] == "Downtown"
