"""Owner vs. network in the export (spec 2026-09-23-ownership-layers-design.md)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tc_core.claims import NETWORK_LABEL, record_claim
from tc_core.db import init_db
from tc_core.export import export_artifacts

CANARY = "CANARY-7f3a tenant in unit 4 said so"


def _seed(conn, tmp_path: Path) -> str:
    conn.executemany(
        "INSERT INTO landlords (landlord_id, display_name, owner_key, created_at, updated_at) "
        "VALUES (?, ?, ?, 'now', 'now')",
        [(1, "Willow Lane Apartments Inc", "willow-lane-apartments-inc"),
         (2, "Kruthaups Holding Ltd", "kruthaups-holding-ltd"),
         (3, "Solo Rentals Ltd", "solo-rentals-ltd")],
    )
    conn.executemany(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, landlord_id, "
        "created_at, updated_at) VALUES (?, ?, 49.28, -123.1, 'Mount Pleasant', 20, ?, 'now', 'now')",
        [("522 e 8th ave", "522 e 8th ave", 1),
         ("525 w 14th ave", "525 w 14th ave", 2),
         ("1 solo st", "1 solo st", 3),
         ("2 solo st", "2 solo st", 3),
         ("3 nobody st", "3 nobody st", None)],
    )
    conn.executemany(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, order_created_date, "
        "data_fetch_status, ingested_at) VALUES (?, ?, '2026-05-28 16:10:39.862', 'SUCCESS', 'now')",
        [("008-173-613", "ST. GEORGE ESTATES LTD."),
         ("007-265-280", "GLR PROPERTIES LTD."),
         ("007-265-281", "GLR PROPERTIES LTD.")],
    )
    conn.execute(
        "INSERT INTO raw_buildings (address, bsns_year, ingested_at) "
        "VALUES ('522 e 8th ave', 2026, 'now')"
    )
    conn.execute(
        "INSERT INTO overlay_housing (addr_key, address, housing_name, local_area, lat, lon, "
        "is_coop, is_sro, ingested_at) VALUES ('999 nowhere rd', '999 nowhere rd', 'Elm Co-op', "
        "'Mount Pleasant', 49.3, -123.15, 1, 0, 'now')"
    )
    for a, b in (("GLR PROPERTIES LTD.", "RENER, GEORGE"), ("ST. GEORGE ESTATES LTD.", "RENER, GEORGE")):
        record_claim(conn, a, b, "common_owner", "public_registry", confidence="confirmed")
    record_claim(conn, "GLR PROPERTIES LTD.", "ST. GEORGE ESTATES LTD.", "common_owner",
                 "tenant_report", confidence="confirmed", source_note=CANARY)
    conn.commit()
    pid_map = tmp_path / "pid_address_map.csv"
    pid_map.write_text(
        "pid,address_point_id,address,addr_key,local_area,lat_lon\n"
        '008173613,1,522 e 8th ave,522 e 8th ave,Mount Pleasant,"49.28,-123.1"\n'
        '007265280,2,525 w 14th ave,525 w 14th ave,Mount Pleasant,"49.28,-123.1"\n'
        '007265281,3,999 not rental st,999 not rental st,Mount Pleasant,"49.28,-123.1"\n',
        encoding="utf-8",
    )
    return str(pid_map)


def _export(tmp_path: Path, extra=None) -> Path:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    pid_map = _seed(conn, tmp_path)
    if extra:
        extra(conn)
    out = tmp_path / "out"
    export_artifacts(conn, out, pid_address_map_path=pid_map)
    return out


def _records(out: Path) -> dict:
    data = json.loads((out / "building_records.json").read_text())
    return {r["address"]: r for r in data["records"].values()}


def test_building_owner_is_its_registry_body_within_a_claims_network(tmp_path):
    rec = _records(_export(tmp_path))["522 e 8th ave"]
    assert (rec["owner_name"], rec["owner_key"], rec["owner_source"]) == (
        "ST. GEORGE ESTATES LTD.", "st-george-estates-ltd", "registry")
    assert rec["registered_owners"] == ["ST. GEORGE ESTATES LTD."]
    assert rec["registry_pids"] == ["008-173-613"]
    assert rec["registry_retrieved"] == "2026-05-28"
    assert rec["licence_holder"] == "Willow Lane Apartments Inc"
    assert (rec["network_key"], rec["network_name"], rec["network_source"], rec["network_name_source"]) == (
        "net:glr-properties-ltd", "GLR PROPERTIES LTD.", "claims", "default")
    assert rec["network_entities"] == ["GLR PROPERTIES LTD.", "RENER, GEORGE", "ST. GEORGE ESTATES LTD."]
    assert rec["network_buildings_on_map"] == 2
    assert rec["network_properties_on_title"] == 3
    assert rec["network_evidence"] == {"registry": 2, "vtu_research": 1}


def test_licence_only_buildings_fall_back_to_the_licence_holder(tmp_path):
    rec = _records(_export(tmp_path))["1 solo st"]
    assert (rec["owner_name"], rec["owner_key"], rec["owner_source"]) == (
        "Solo Rentals Ltd", "solo-rentals-ltd", "licence")
    assert rec["registered_owners"] == [] and rec["registry_pids"] == []
    assert rec["registry_retrieved"] is None
    assert (rec["network_key"], rec["network_name"], rec["network_source"]) == (
        "solo-rentals-ltd", "Solo Rentals Ltd", "licence")
    assert rec["network_buildings_on_map"] == 2
    assert rec["network_properties_on_title"] is None
    assert rec["network_entities"] is None and rec["network_evidence"] is None
    assert rec["network_name_source"] is None


def test_unknown_owners_carry_no_source_and_no_network_size(tmp_path):
    recs = _records(_export(tmp_path))
    for address in ("3 nobody st", "999 nowhere rd"):
        rec = recs[address]
        assert (rec["owner_name"], rec["owner_key"]) == ("(Unknown)", "unknown"), address
        assert rec["owner_source"] is None and rec["network_source"] is None, address
        assert rec["network_buildings_on_map"] is None, address


def test_network_label_claim_renames_the_network_but_not_its_key(tmp_path):
    def label(conn):
        record_claim(conn, "RENER, GEORGE", "GLR Properties / Rener family", NETWORK_LABEL,
                     "manual_research", confidence="confirmed")

    rec = _records(_export(tmp_path, label))["525 w 14th ave"]
    assert (rec["network_name"], rec["network_name_source"], rec["network_key"]) == (
        "GLR Properties / Rener family", "claim", "net:glr-properties-ltd")


def test_marker_metadata_carries_both_keys(tmp_path):
    markers = json.loads((_export(tmp_path) / "marker_metadata.json").read_text())["markers"]
    by_owner = {m["owner_key"]: m for m in markers}
    assert by_owner["st-george-estates-ltd"]["network_key"] == "net:glr-properties-ltd"


def test_filter_config_carries_the_licence_year(tmp_path):
    cfg = json.loads((_export(tmp_path) / "filter_config.json").read_text())
    assert cfg["licence_year"] == 2026


def test_licence_holder_named_like_a_claims_network_stays_a_separate_network(tmp_path):
    """A licence-only landlord whose name sanitizes to a claims network's
    default key must not merge into that network's key or inflate its count."""
    def lookalike(conn):
        conn.execute(
            "INSERT INTO landlords (landlord_id, display_name, owner_key, created_at, updated_at) "
            "VALUES (4, 'Glr Properties Ltd', 'glr-properties-ltd', 'now', 'now')"
        )
        conn.execute(
            "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, landlord_id, "
            "created_at, updated_at) VALUES ('7 lookalike st', '7 lookalike st', 49.28, -123.1, "
            "'Mount Pleasant', 10, 4, 'now', 'now')"
        )

    recs = _records(_export(tmp_path, lookalike))
    network = recs["522 e 8th ave"]
    licence = recs["7 lookalike st"]
    assert network["network_key"] != licence["network_key"]
    assert network["network_buildings_on_map"] == 2
    assert licence["network_buildings_on_map"] == 1


def test_claim_source_notes_never_reach_any_artifact(tmp_path):
    """Guard: passes before and after this change. Notes can identify tenants
    (CLAUDE.md §11), so no artifact may ever contain one."""
    out = _export(tmp_path)
    for path in out.iterdir():
        assert "CANARY-7f3a" not in path.read_text(encoding="utf-8"), path.name
