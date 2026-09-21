import json
import sqlite3

from sica_core.db import init_db
from sica_core.export import export_artifacts


def _seed(conn):
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, "
        "year_built, created_at, updated_at) VALUES ('100 main st', '100 main st', "
        "49.28, -123.1, 'Downtown', 50, 1970, 'now', 'now')"
    )
    conn.execute(
        "INSERT INTO blocks (block_id, geom, ingested_at) VALUES (1, "
        "'{\"type\":\"Polygon\",\"coordinates\":[[[-123.2,49.2],[-123.2,49.4],"
        "[-123.0,49.4],[-123.0,49.2],[-123.2,49.2]]]}', 'now')"
    )
    conn.commit()


def test_writes_all_artifacts(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    export_artifacts(conn, tmp_path)

    for name in (
        "filter_config.json",
        "marker_metadata.json",
        "building_records.json",
        "blocks.geojson",
    ):
        assert (tmp_path / name).exists(), name


def test_copies_the_boundary_geojson_through(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)
    src = tmp_path / "src-boundary.geojson"
    src.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    out = tmp_path / "artifacts"

    export_artifacts(conn, out, boundary_geojson_path=str(src))

    copied = json.loads((out / "local-area-boundary.geojson").read_text())
    assert copied["type"] == "FeatureCollection"


def test_marker_metadata_carries_coordinates(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    export_artifacts(conn, tmp_path)

    meta = json.loads((tmp_path / "marker_metadata.json").read_text())
    assert meta["schema_version"] == 1
    record = meta["markers"][0]
    assert record["lat"] == 49.28
    assert record["lon"] == -123.1


def test_blocks_geojson_is_a_feature_collection(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    export_artifacts(conn, tmp_path)

    gj = json.loads((tmp_path / "blocks.geojson").read_text())
    assert gj["type"] == "FeatureCollection"
    feature = gj["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert "block_label" in feature["properties"]
    assert "member_share" in feature["properties"]


def test_matched_building_carries_overlay_data(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, "
        "year_built, is_sro, sro_owner, created_at, updated_at) VALUES "
        "('200 side st', '200 side st', 49.29, -123.11, 'Downtown', 30, 1965, "
        "1, 'Owner Co', 'now', 'now')"
    )
    conn.commit()

    export_artifacts(conn, tmp_path)

    meta = json.loads((tmp_path / "marker_metadata.json").read_text())
    marker = next(m for m in meta["markers"] if m["b_id"] == 1)
    assert marker["housing_type"] == "sro"

    records = json.loads((tmp_path / "building_records.json").read_text())
    building = records["records"]["1"]
    assert building["sro_owner"] == "Owner Co"


def _seed_with_overlay(conn):
    _seed(conn)
    conn.execute(
        "INSERT INTO overlay_housing (addr_key, address, housing_name, local_area, "
        "lat, lon, is_coop, is_sro, source_row_ids, ingested_at) VALUES "
        "('999 nowhere rd', '999 Nowhere Rd', 'Elm Co-op', 'Downtown', 49.3, "
        "-123.15, 1, 0, '{\"raw_coops\": [7]}', 'now')"
    )
    conn.commit()


def test_building_records_columns_are_the_public_list(tmp_path):
    """The `columns` array drives the user-facing CSV export, so it is an
    explicit list: no lineage/ingest internals, no per-member payloads."""
    from sica_core.export import BUILDING_RECORD_COLUMNS

    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_with_overlay(conn)

    export_artifacts(conn, tmp_path)

    data = json.loads((tmp_path / "building_records.json").read_text())
    assert data["columns"] == BUILDING_RECORD_COLUMNS
    for rec in data["records"].values():
        assert list(rec) == BUILDING_RECORD_COLUMNS
    for internal in ("members_payload", "_overlay_id", "source_row_ids",
                     "ingested_at", "created_at", "updated_at", "member_share_building"):
        assert internal not in data["columns"]
    assert data["records"]["1"]["member_share_pct"] == 0


def test_overlay_rows_reach_the_artifacts_with_their_source(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_with_overlay(conn)

    export_artifacts(conn, tmp_path)

    markers = json.loads((tmp_path / "marker_metadata.json").read_text())["markers"]
    by_source = {m["source"]: m for m in markers}
    assert set(by_source) == {"building", "overlay_coop"}
    assert by_source["overlay_coop"]["housing_type"] == "co-op"
    records = json.loads((tmp_path / "building_records.json").read_text())["records"]
    overlay = records[str(by_source["overlay_coop"]["b_id"])]
    assert overlay["housing_name"] == "Elm Co-op"
    assert overlay["source"] == "overlay_coop"
