"""Property-manager listing snapshots (data/raw/property_managers/<slug>/<date>.json)
accumulate in raw_manager_listings: one row per listing, with the first and
last snapshot it appeared in."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tc_core.db import get_connection, init_db
from tc_core.ingest.manager_listings import ingest_manager_listings


def _listing(pid, name, address):
    return {
        "id": pid, "name": name, "permalink": f"https://example.org/{pid}",
        "address": {"address": address, "city": "Vancouver"},
        "client": {"id": 118, "name": "Tribe Rentals"},
        "contact": {"name": "Staff Person", "phone": "604-000-0000", "email": "staff@example.org"},
    }


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
