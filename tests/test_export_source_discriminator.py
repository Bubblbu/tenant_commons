import sqlite3

import pandas as pd

from tc_core.db import init_db
from tc_core.export import reconstruct_blocks, reconstruct_filter_config, reconstruct_points


def _seed(conn):
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, "
        "created_at, updated_at) "
        "VALUES ('100 main st', '100 main st', 49.28, -123.1, 'Downtown', 50, 'now', 'now')"
    )
    conn.execute(
        "INSERT INTO overlay_housing (addr_key, address, housing_name, local_area, "
        "lat, lon, is_coop, is_sro, ingested_at) "
        "VALUES ('999 nowhere rd', '999 nowhere rd', 'Elm Co-op', 'Downtown', "
        "49.3, -123.15, 1, 0, 'now')"
    )
    conn.execute(
        "INSERT INTO overlay_housing (addr_key, address, housing_name, local_area, "
        "lat, lon, is_coop, is_sro, ingested_at) "
        "VALUES ('888 elsewhere st', '888 elsewhere st', 'Old Rooms', 'Downtown', "
        "49.31, -123.16, 0, 1, 'now')"
    )
    conn.commit()


def test_source_distinguishes_buildings_from_overlay_records():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    pts = reconstruct_points(conn, pd.Timestamp("2026-09-20", tz="UTC"))

    assert set(pts["source"]) == {"building", "overlay_coop", "overlay_sro"}
    assert (pts.loc[pts["source"] == "building", "addr_key"] == "100 main st").all()


def test_b_id_is_unique_across_both_origins():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    pts = reconstruct_points(conn, pd.Timestamp("2026-09-20", tz="UTC"))

    assert pts["b_id"].is_unique
    assert len(pts) == 3


def test_overlay_rows_have_no_units_or_owner():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    pts = reconstruct_points(conn, pd.Timestamp("2026-09-20", tz="UTC"))
    overlay = pts[pts["source"] != "building"]

    assert overlay["units"].isna().all()
    assert (overlay["owner_group"] == "(Unknown)").all()
    assert (overlay["member_count"] == 0).all()


def test_filter_config_counts_only_buildings():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    now = pd.Timestamp("2026-09-20", tz="UTC")
    pts = reconstruct_points(conn, now)
    blocks = reconstruct_blocks(conn, pts)
    cfg = reconstruct_filter_config(conn, pts, blocks, now)

    assert cfg["dataset_totals"]["buildings"] == 1
    downtown = next(n for n in cfg["neighbourhoods"] if n["name"] == "Downtown")
    assert downtown["count"] == 1
