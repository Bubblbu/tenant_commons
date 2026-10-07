"""Usable landlord listings add the buildings the City's sources don't list,
placed on a City address point and never naming an owner (spec
2026-09-30-landlord-listings-source-design.md, section 2)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tc_core.db import get_connection, init_db
from tc_core.ingest.listing_buildings import BUILDING_SOURCE, listing_building_rows
from tc_core.ingest.merge import _prepare_addresses, load_raw_frames, merge_and_dedupe_buildings

NOW = "2026-09-30T00:00:00+00:00"


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def _point(conn, civic, street, lat, lon, area="West End"):
    conn.execute(
        "INSERT INTO raw_addresses (civic_number, std_street, geo_point_2d, geo_local_area, ingested_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (civic, street, f"{lat}, {lon}", area, NOW),
    )


def _listing(row_id, address, units=None, manager="Wall Financial Corporation"):
    return {"listing_row_id": row_id, "manager": manager, "name": None, "address": address,
            "url": f"https://example.org/{row_id}", "last_seen": "2026-09-30", "units": units}


def _points(conn):
    _, raw_addresses = load_raw_frames(conn)
    return _prepare_addresses(raw_addresses)


def test_an_unlisted_building_on_an_address_point_is_added():
    conn = _conn()
    _point(conn, "1120", "PACIFIC ST", 49.2783, -123.1335)
    rows = listing_building_rows([_listing(7, "1120 Pacific Street", units=120)], set(), {}, _points(conn))
    assert len(rows) == 1
    row = rows.row(0, named=True)
    assert row["addr_key"] == "1120 pacific st"
    assert (row["lat"], row["lon"]) == (49.2783, -123.1335)
    assert row["local_area"] == "West End"
    assert row["units"] == 120
    assert row["building_source"] == BUILDING_SOURCE == "manager listing"
    assert (row["owner_group"], row["owner_key"]) == ("(Unknown)", "unknown")
    assert json.loads(row["source_row_ids"]) == {"raw_manager_listings": [7]}


def test_a_listing_without_an_address_point_adds_nothing():
    conn = _conn()
    _point(conn, "1120", "PACIFIC ST", 49.2783, -123.1335)
    assert listing_building_rows([_listing(7, "6000 Wesbrook Mall")], set(), {}, _points(conn)).is_empty()


def test_a_listing_matching_a_known_building_adds_nothing_even_by_street_type_typo():
    conn = _conn()
    _point(conn, "1333", "JERVIS ST", 49.28, -123.13)
    known = {"1333 jervis st"}
    rows = listing_building_rows([_listing(1, "1333 Jervis Avenue")], known, {}, _points(conn))
    assert rows.is_empty()


def test_a_listing_at_a_secondary_address_adds_nothing():
    conn = _conn()
    _point(conn, "936", "BUTE ST", 49.28, -123.13)
    rows = listing_building_rows(
        [_listing(1, "936 Bute Street")], {"958 bute st"}, {"936 bute st": "958 bute st"}, _points(conn),
    )
    assert rows.is_empty()


def test_two_companies_listing_one_new_address_make_one_building():
    conn = _conn()
    _point(conn, "455", "ABBOTT ST", 49.28, -123.10)
    rows = listing_building_rows(
        [_listing(3, "455 Abbott Street", units=80, manager="Tribe Rentals"),
         _listing(4, "455 Abbott St", units=82)],
        set(), {}, _points(conn),
    )
    assert len(rows) == 1
    assert rows["units"][0] == 82
    assert json.loads(rows["source_row_ids"][0]) == {"raw_manager_listings": [3, 4]}


def test_city_sources_win_and_listings_fill_the_gaps():
    conn = _conn()
    _point(conn, "1220", "CARDERO ST", 49.29, -123.14)
    _point(conn, "1120", "PACIFIC ST", 49.2783, -123.1335)
    conn.execute(
        "INSERT INTO raw_buildings (raw_building_id, address, local_area, units, building_source, ingested_at) "
        "VALUES (1, '1220 cardero st', 'West End', 30, 'rental licence', ?)", (NOW,),
    )
    raw_buildings, raw_addresses = load_raw_frames(conn)
    out = merge_and_dedupe_buildings(
        raw_buildings, raw_addresses,
        listings=[_listing(1, "1220 Cardero Street", units=99), _listing(2, "1120 Pacific Street")],
        secondary_index={},
    )
    by_key = {r["addr_key"]: r for r in out.iter_rows(named=True)}
    assert set(by_key) == {"1220 cardero st", "1120 pacific st"}
    assert by_key["1220 cardero st"]["building_source"] == "rental licence"
    assert by_key["1220 cardero st"]["units"] == 30
    assert by_key["1120 pacific st"]["building_source"] == "manager listing"


def test_merge_without_listings_is_unchanged():
    conn = _conn()
    _point(conn, "1220", "CARDERO ST", 49.29, -123.14)
    conn.execute(
        "INSERT INTO raw_buildings (raw_building_id, address, local_area, ingested_at) "
        "VALUES (1, '1220 cardero st', 'West End', ?)", (NOW,),
    )
    raw_buildings, raw_addresses = load_raw_frames(conn)
    assert list(merge_and_dedupe_buildings(raw_buildings, raw_addresses)["addr_key"]) == ["1220 cardero st"]


def test_added_from_listings_names_each_added_building_and_its_lister():
    from tc_core.ingest.listing_buildings import added_from_listings

    conn = _conn()
    conn.executemany(
        "INSERT INTO buildings (building_id, addr_key, address, building_source, source_row_ids, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, '[]', ?, ?)",
        [(1, "1120 pacific st", "1120 pacific st", "manager listing", NOW, NOW),
         (2, "1220 cardero st", "1220 cardero st", "rental licence", NOW, NOW)],
    )
    conn.executemany(
        "INSERT INTO building_listings (building_id, manager, url, last_seen, listing_row_id) VALUES (?, ?, ?, ?, ?)",
        [(1, "Wall Financial Corporation", "https://example.org/1", "2026-09-30", 1),
         (2, "Tribe Rentals", "https://example.org/2", "2026-09-30", 2)],
    )
    assert added_from_listings(conn) == [("Wall Financial Corporation", "1120 pacific st")]
