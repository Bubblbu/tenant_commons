"""Per-building registered owners from the BC Land Owner Transparency
Registry (spec 2026-09-23-ownership-layers-design.md §3)."""

from __future__ import annotations

from tc_core.db import get_connection, init_db
from tc_core.metrics.registry_owners import build_registry_owners


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def _lotr(conn, pid, name, created="2026-05-28 16:10:39.862", status="SUCCESS"):
    conn.execute(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, order_created_date, "
        "data_fetch_status, ingested_at) VALUES (?, ?, ?, ?, 'now')",
        (pid, name, created, status),
    )


def _pid_map(tmp_path, rows):
    path = tmp_path / "pid_address_map.csv"
    lines = ["pid,address_point_id,address,addr_key,local_area,lat_lon"]
    lines += [f'{pid},1,{key},{key},West End,"49.28,-123.13"' for pid, key in rows]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def test_primary_owner_holds_the_most_pids(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-001", "SMALL LTD")
    _lotr(conn, "001-000-002", "BIG LTD")
    _lotr(conn, "001-000-003", "BIG LTD")
    owners = build_registry_owners(conn, _pid_map(
        tmp_path, [("001000001", "1 a st"), ("001000002", "1 a st"), ("001000003", "1 a st")]))
    assert owners["1 a st"].owners == ["BIG LTD", "SMALL LTD"]


def test_equal_pid_counts_break_alphabetically(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-001", "ZED LTD")
    _lotr(conn, "001-000-002", "ALPHA LTD")
    owners = build_registry_owners(conn, _pid_map(
        tmp_path, [("001000001", "1 a st"), ("001000002", "1 a st")]))
    assert owners["1 a st"].owners == ["ALPHA LTD", "ZED LTD"]


def test_spelling_variants_are_one_owner_shown_by_the_commonest_spelling(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-001", "GLR PROPERTIES LTD.")
    _lotr(conn, "001-000-001", "GLR PROPERTIES LTD.")
    _lotr(conn, "001-000-002", "GLR PROPERTIES LTD")
    owners = build_registry_owners(conn, _pid_map(
        tmp_path, [("001000001", "1 a st"), ("001000002", "1 a st")]))
    assert owners["1 a st"].owners == ["GLR PROPERTIES LTD."]


def test_pids_as_filed_and_latest_retrieval_date(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-002", "A LTD", created="2026-05-28 16:10:39.862")
    _lotr(conn, "001-000-001", "A LTD", created="2026-08-19 16:23:53.762")
    owners = build_registry_owners(conn, _pid_map(
        tmp_path, [("001000001", "1 a st"), ("001000002", "1 a st")]))
    assert owners["1 a st"].pids == ["001-000-001", "001-000-002"]
    assert owners["1 a st"].retrieved == "2026-08-19"


def test_failed_fetches_and_unmapped_pids_are_ignored(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-001", "A LTD", status="FAILED")
    _lotr(conn, "009-999-999", "B LTD")
    owners = build_registry_owners(conn, _pid_map(tmp_path, [("001000001", "1 a st")]))
    assert owners == {}


def test_building_reaches_its_owner_through_its_own_pid(tmp_path):
    # 512 Campbell Ave sits on the 500 Campbell Ave parcel: only the building
    # record carries the PID, the City's address points don't.
    conn = _conn()
    _lotr(conn, "001-000-001", "A LTD")
    conn.execute(
        "INSERT INTO raw_buildings (address, pid, ingested_at) VALUES ('512 Campbell Ave', '001000001', 'now')"
    )
    owners = build_registry_owners(conn, _pid_map(tmp_path, [("001000001", "500 campbell ave")]))
    assert owners["512 campbell ave"].owners == ["A LTD"]
    assert owners["500 campbell ave"].owners == ["A LTD"]


def test_every_address_point_of_a_pid_gets_its_owner(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-001", "A LTD")
    owners = build_registry_owners(conn, _pid_map(
        tmp_path, [("001000001", "1200 alberni st"), ("001000001", "1202 alberni st")]))
    assert set(owners) == {"1200 alberni st", "1202 alberni st"}
