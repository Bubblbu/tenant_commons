"""City-owned land: buildings whose folio's land coordinate (its first 8
digits) is on the City's list (spec 2026-10-20)."""

from __future__ import annotations

from tc_core.db import get_connection, init_db
from tc_core.ingest.raw_city_owned import ingest_raw_city_owned
from tc_core.metrics.sector import city_owned_buildings


def test_buildings_on_city_land_are_found_by_land_coordinate(tmp_path):
    conn = get_connection(":memory:")
    init_db(conn)
    src = tmp_path / "city-owned-properties.csv"
    src.write_text(
        "﻿building_no;sap_address;geom;geo_local_area;land_coord;type;geo_point_2d\n"
        '1;1800 BEACH;"{}";West End;61210904;CAPITAL FUND;"49.2, -123.1"\n'
        '2;5900 BALACLAVA;"{}";Kerrisdale;05475575;VAHEF;"49.2, -123.1"\n',
        encoding="utf-8",
    )
    assert ingest_raw_city_owned(conn, str(src)) == 2
    conn.executemany(
        "INSERT INTO raw_buildings (raw_building_id, address, folio, ingested_at) VALUES (?, ?, ?, 'now')",
        [(1, "1800 beach ave", "612109040000"), (2, "5900 balaclava st", "054755750000;999999990000"),
         (3, "1 private st", "111111110000")],
    )
    conn.executemany(
        "INSERT INTO buildings (building_id, addr_key, address, source_row_ids, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'now', 'now')",
        [(10, "a", "a", "[1]"), (11, "b", "b", "[2]"), (12, "c", "c", "[3]")],
    )
    assert city_owned_buildings(conn) == {10, 11}
