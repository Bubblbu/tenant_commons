"""Every name a source gives a building is kept with its source
(building_names); the map shows one, operating names first."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tc_core.db import get_connection, init_db
from tc_core.ingest.building_names import derive_building_names, pick_building_name

NOW = "2026-01-01T00:00:00+00:00"


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def _building(conn, bid, addr_key, raw_id, *, foi_name=None, name=None, trade=None, secondary=None):
    conn.execute(
        "INSERT INTO raw_buildings (raw_building_id, address, secondary_addresses, foi_name, name, bsns_trade_name, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (raw_id, addr_key, secondary, foi_name, name, trade, NOW),
    )
    conn.execute(
        "INSERT INTO buildings (building_id, addr_key, address, source_row_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (bid, addr_key, addr_key, json.dumps([raw_id]), NOW, NOW),
    )


def _listing(conn, external_id, name, address):
    conn.execute(
        "INSERT INTO raw_manager_listings (manager, external_id, name, address, first_seen, last_seen) "
        "VALUES ('Tribe Rentals', ?, ?, ?, '2026-09-24', '2026-09-24')",
        (external_id, name, address),
    )


def test_names_from_every_source_are_kept_with_their_source():
    conn = _conn()
    _building(conn, 1, "1265 beach ave", 10, foi_name="Penthouse Towers", trade="Penthouse Towers Apts;Beach Annex")
    _building(conn, 2, "1346 w 13th ave", 11, name="Villa Paloma Housing")
    _listing(conn, "7", "Villa Paloma", "1346 West 13th Avenue")  # spelled-out direction still matches
    n = derive_building_names(conn)
    rows = set(conn.execute("SELECT building_id, name, source_type FROM building_names"))
    assert rows == {
        (1, "Penthouse Towers", "foi_rental_list"),
        (1, "Penthouse Towers Apts", "licence_trade_name"),
        (1, "Beach Annex", "licence_trade_name"),
        (2, "Villa Paloma Housing", "non_market_list"),
        (2, "Villa Paloma", "manager_listing"),
    }
    assert n == 5


def test_unmatched_listings_add_no_names():
    conn = _conn()
    _building(conn, 1, "1265 beach ave", 10)
    _listing(conn, "8", "Elsewhere", "455 Abbott Street")
    derive_building_names(conn)
    assert conn.execute("SELECT count(*) FROM building_names").fetchone()[0] == 0


def test_operating_names_come_first_and_spellings_collapse():
    name, others = pick_building_name([
        ("Stamp's Place", "non_market_list"),
        ("Stamps Place", "licence_trade_name"),
        ("STAMPS PLACE", "foi_rental_list"),
        ("Campbell Residence", "foi_rental_list"),
    ])
    assert name == "Stamps Place"
    assert others == ["Campbell Residence"]


def test_no_names_means_no_name():
    assert pick_building_name([]) == (None, [])


def test_export_names_buildings_from_the_table_and_overlays_from_their_own_name():
    import pandas as pd

    from tc_core.export import apply_building_names

    df = pd.DataFrame([
        {"b_id": 1, "source": "building", "housing_name": None},
        {"b_id": 2, "source": "building", "housing_name": None},
        {"b_id": 1, "source": "overlay_sro", "housing_name": "Hotel Example"},  # overlay ids can repeat building ids' range
    ])
    apply_building_names(df, {1: [("Maple Apartments", "manager_listing"), ("Maple", "foi_rental_list")]})
    assert df["building_name"].tolist() == ["Maple Apartments", None, "Hotel Example"]
    assert df["other_names"].tolist() == [["Maple"], [], []]


def test_a_rebuild_succeeds_when_building_names_hold_rows():
    conn = _conn()
    _building(conn, 1, "1265 beach ave", 10, foi_name="Penthouse Towers")
    derive_building_names(conn)
    init_db(conn)  # drops and recreates buildings; must not trip building_names' foreign key
    assert conn.execute("SELECT count(*) FROM building_names").fetchone()[0] == 0
