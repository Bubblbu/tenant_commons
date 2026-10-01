"""Property-manager listing snapshots (data/raw/property_managers/<slug>/<date>.json)
accumulate in raw_manager_listings: one row per listing, with the first and
last snapshot it appeared in."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tc_core.db import get_connection, init_db
from tc_core.ingest.manager_listings import ingest_manager_listings, usable_listings


def _listing(pid, name, address, city="Vancouver", **extra):
    item = {
        "id": pid, "name": name, "permalink": f"https://example.org/{pid}",
        "address": {"address": address, "city": city},
        "client": {"id": 118, "name": "Tribe Rentals"},
        "contact": {"name": "Staff Person", "phone": "604-000-0000", "email": "staff@example.org"},
    }
    item.update(extra)
    return item


def _snapshot(root, date, listings):
    d = root / "tribe"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{date}.json").write_text(json.dumps(listings))


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def test_listings_keep_first_and_last_seen_across_snapshots(tmp_path):
    _snapshot(tmp_path, "2026-09-01", [_listing(1, "Maple Apartments", "1220 Cardero Street"), _listing(2, "Gone Manor", "1 Gone St")])
    _snapshot(tmp_path, "2026-09-24", [_listing(1, "Maple Apartments", "1220 Cardero Street")])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    rows = {r[0]: r[1:] for r in conn.execute(
        "SELECT external_id, manager, name, address, url, first_seen, last_seen FROM raw_manager_listings")}
    assert rows["1"] == ("Tribe Rentals", "Maple Apartments", "1220 Cardero Street", "https://example.org/1", "2026-09-01", "2026-09-24")
    assert rows["2"][-2:] == ("2026-09-01", "2026-09-01")


def test_reingesting_is_idempotent_and_survives_a_rebuild(tmp_path):
    _snapshot(tmp_path, "2026-09-24", [_listing(1, "Maple Apartments", "1220 Cardero Street")])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    ingest_manager_listings(conn, str(tmp_path))
    init_db(conn)
    assert conn.execute("SELECT count(*) FROM raw_manager_listings").fetchone()[0] == 1


def test_staff_contact_details_are_not_stored(tmp_path):
    _snapshot(tmp_path, "2026-09-24", [_listing(1, "Maple Apartments", "1220 Cardero Street")])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    dump = "\n".join(conn.iterdump())
    assert "Staff Person" not in dump and "staff@example.org" not in dump


def test_listings_outside_vancouver_are_skipped(tmp_path):
    _snapshot(tmp_path, "2026-09-30", [
        _listing(1, "Maple Apartments", "1220 Cardero Street"),
        _listing(2, "Glenwood Manor", "1234 Fort Street", city="Victoria"),
    ])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    assert [r[0] for r in conn.execute("SELECT external_id FROM raw_manager_listings")] == ["1"]


def test_status_and_units_are_stored_and_the_newer_snapshot_wins(tmp_path):
    _snapshot(tmp_path, "2026-09-01", [_listing(1, "Amber Lodge", "1045 W 14th Ave", status="In Development")])
    _snapshot(tmp_path, "2026-09-30", [_listing(1, "Amber Lodge", "1045 W 14th Ave", status="Now Renting", units=120)])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    assert conn.execute("SELECT status, units FROM raw_manager_listings").fetchone() == ("Now Renting", 120)


def test_init_db_adds_the_new_columns_to_an_existing_table(tmp_path):
    conn = get_connection(":memory:")
    conn.execute(
        "CREATE TABLE raw_manager_listings (listing_row_id INTEGER PRIMARY KEY, manager TEXT NOT NULL, "
        "external_id TEXT NOT NULL, name TEXT, address TEXT, url TEXT, first_seen TEXT NOT NULL, "
        "last_seen TEXT NOT NULL, UNIQUE (manager, external_id))"
    )
    conn.execute(
        "INSERT INTO raw_manager_listings (manager, external_id, first_seen, last_seen) "
        "VALUES ('Tribe Rentals', '1', '2026-09-01', '2026-09-01')"
    )
    init_db(conn)
    init_db(conn)  # a second run must not try to add the columns again
    cols = {r[1] for r in conn.execute("PRAGMA table_info(raw_manager_listings)")}
    assert {"status", "units"} <= cols
    assert conn.execute("SELECT count(*) FROM raw_manager_listings").fetchone()[0] == 1


def test_usable_listings_are_current_and_built(tmp_path):
    _snapshot(tmp_path, "2026-09-01", [_listing(1, "Gone Manor", "1 Gone St")])
    _snapshot(tmp_path, "2026-09-30", [
        _listing(2, "Maple Apartments", "1220 Cardero Street", units=40),
        _listing(3, "Hornby & Drake", "1300 Hornby St", status=" in development "),
        _listing(4, "Next Year", "2 Future St", status="Coming Soon"),
    ])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    usable = usable_listings(conn)
    assert [u["name"] for u in usable] == ["Maple Apartments"]
    assert usable[0]["last_seen"] == "2026-09-30" and usable[0]["units"] == 40
    assert set(usable[0]) == {"listing_row_id", "manager", "name", "address", "url", "last_seen", "units"}


def test_current_is_judged_per_manager(tmp_path):
    _snapshot(tmp_path, "2026-09-24", [_listing(1, "Maple Apartments", "1220 Cardero Street")])
    other = tmp_path / "dorset"
    other.mkdir()
    (other / "2026-09-30.json").write_text(json.dumps([
        {**_listing(9, "Ocean Crest", "1333 Jervis Street"), "client": {"name": "Dorset Realty Group"}},
    ]))
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    assert sorted(u["name"] for u in usable_listings(conn)) == ["Maple Apartments", "Ocean Crest"]


def test_an_all_out_of_town_snapshot_does_not_keep_stale_listings_current(tmp_path):
    _snapshot(tmp_path, "2026-09-01", [_listing(1, "Maple Apartments", "1220 Cardero Street")])
    _snapshot(tmp_path, "2026-09-30", [_listing(2, "Glenwood", "1234 Fort Street", city="Victoria")])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    # The 2026-09-30 snapshot stored nothing, so 2026-09-01 is still this manager's latest
    # stored date: the listing stays usable. This pins the current, documented behaviour.
    assert [u["name"] for u in usable_listings(conn)] == ["Maple Apartments"]
