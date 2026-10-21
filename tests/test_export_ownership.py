"""Owner vs. network in the export (spec 2026-09-23-ownership-layers-design.md)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from contract_helpers import network, networks, owner, parties, records

from tc_core.claims import ENTITY_KIND, INSTITUTIONAL, NETWORK_LABEL, record_claim
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


def _export(tmp_path: Path, extra=None, **kwargs) -> Path:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    pid_map = _seed(conn, tmp_path)
    if extra:
        extra(conn)
    out = tmp_path / "out"
    export_artifacts(conn, out, pid_address_map_path=pid_map, **kwargs)
    return out


def test_building_owner_is_its_registry_body_within_a_claims_network(tmp_path):
    out = _export(tmp_path)
    rec = records(out)["522 e 8th ave"]
    o = owner(rec)
    assert (o["name"], o["entity_key"], o["pids"]) == (
        "ST. GEORGE ESTATES LTD.", "st-george-estates-ltd", ["008-173-613"])
    assert o["sources"] == [{"type": "registry", "as_of": "2026-05-28", "url": None}]
    assert [p["name"] for p in parties(rec, "owner")] == ["ST. GEORGE ESTATES LTD."]
    (licensee,) = parties(rec, "licensee")
    assert (licensee["name"], licensee["same_as"]) == ("Willow Lane Apartments Inc", None)
    net = network(out, rec)
    assert (net["id"], net["name"], net["tier"], net["name_source"]) == (
        "net:glr-properties-ltd", "GLR PROPERTIES LTD.", "confirmed", "default")
    assert [(e["name"], e["kind"], e["buildings"]) for e in net["entities"]] == [
        ("RENER, GEORGE", "individual", 0),
        ("GLR PROPERTIES LTD.", "company", 1),
        ("ST. GEORGE ESTATES LTD.", "company", 1),
    ]
    assert net["totals"]["buildings"] == 2
    assert net["totals"]["properties_on_title"] == 3
    assert net["evidence"] == {"registry": 2, "city_records": 0, "vtu_research": 1}


def test_licence_only_buildings_fall_back_to_the_licence_holder(tmp_path):
    out = _export(tmp_path)
    rec = records(out)["1 solo st"]
    o = owner(rec)
    assert (o["name"], o["entity_key"], o["pids"]) == ("Solo Rentals Ltd", "solo-rentals-ltd", [])
    assert [s["type"] for s in o["sources"]] == ["licence"]
    assert parties(rec, "licensee")[0]["same_as"] == "owner"
    assert rec["registry_search"] == {"status": "not_searched", "date": None}
    net = network(out, rec)
    assert (net["id"], net["name"], net["tier"], net["name_source"]) == (
        "solo-rentals-ltd", "Solo Rentals Ltd", "name_match", "default")
    assert net["totals"]["buildings"] == 2
    assert net["totals"]["properties_on_title"] is None
    assert net["entities"] == [] and net["evidence"] == {"registry": 0, "city_records": 0, "vtu_research": 0}


def test_unknown_owners_carry_no_owner_and_no_network(tmp_path):
    recs = records(_export(tmp_path))
    for address in ("3 nobody st", "999 nowhere rd"):
        rec = recs[address]
        assert owner(rec) is None, address
        assert rec["network_id"] is None, address


def test_network_label_claim_renames_the_network_but_not_its_key(tmp_path):
    def label(conn):
        record_claim(conn, "RENER, GEORGE", "GLR Properties / Rener family", NETWORK_LABEL,
                     "manual_research", confidence="confirmed")

    out = _export(tmp_path, label)
    net = network(out, records(out)["525 w 14th ave"])
    assert (net["name"], net["name_source"], net["id"]) == (
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

    out = _export(tmp_path, lookalike)
    recs = records(out)
    claims_net = network(out, recs["522 e 8th ave"])
    licence_net = network(out, recs["7 lookalike st"])
    assert claims_net["id"] != licence_net["id"]
    assert claims_net["totals"]["buildings"] == 2
    assert licence_net["totals"]["buildings"] == 1


def test_claim_source_notes_never_reach_any_artifact(tmp_path):
    """Guard: passes before and after this change. Notes can identify tenants
    (CLAUDE.md §11), so no artifact may ever contain one."""
    out = _export(tmp_path)
    for path in out.iterdir():
        assert "CANARY-7f3a" not in path.read_text(encoding="utf-8"), path.name


def test_listings_reach_the_record_under_the_managers_own_name(tmp_path):
    managers = tmp_path / "property_managers.toml"
    managers.write_text('[[manager]]\nname = "Tribe Rental Management"\nlisting_names = ["Tribe Rentals"]\n')

    def extra(conn):
        bid = conn.execute("SELECT building_id FROM buildings WHERE addr_key = '1 solo st'").fetchone()[0]
        conn.executemany(
            "INSERT INTO building_listings (building_id, manager, url, last_seen, listing_row_id) VALUES (?, ?, ?, ?, ?)",
            [(bid, "Tribe Rentals", "https://example.org/1", "2026-09-30", 1),
             (bid, "Wall Financial Corporation", "https://example.org/w", "2026-09-30", 2)],
        )

    recs = records(_export(tmp_path, extra, property_managers_path=str(managers)))
    rec = recs["1 solo st"]
    # The known manager first, under its own name; every listing company manages.
    assert [(m["name"], m["sources"]) for m in parties(rec, "manager")] == [
        ("Tribe Rental Management", [{"type": "listing", "as_of": "2026-09-30", "url": "https://example.org/1"}]),
        ("Wall Financial Corporation", [{"type": "listing", "as_of": "2026-09-30", "url": "https://example.org/w"}]),
    ]
    assert owner(rec)["name"] == "Solo Rentals Ltd"
    assert parties(recs["2 solo st"], "manager") == [] and parties(recs["999 nowhere rd"], "manager") == []


def test_feed_staff_contacts_never_reach_any_artifact(tmp_path):
    """Snapshots carry staff contacts; only the company's name, page and date
    may reach the map (spec 2026-09-30 section 5)."""
    import json as _json

    from tc_core.ingest.building_names import derive_building_names
    from tc_core.ingest.manager_listings import ingest_manager_listings

    feeds = tmp_path / "feeds" / "tribe"
    feeds.mkdir(parents=True)
    (feeds / "2026-09-30.json").write_text(_json.dumps([{
        "id": 1, "name": "Solo Place", "permalink": "https://example.org/1",
        "address": {"address": "1 Solo St", "city": "Vancouver"},
        "client": {"name": "Tribe Rentals"},
        "contact": {"name": "CANARY-staff Person", "email": "canary-staff@example.org"},
    }]))

    def extra(conn):
        ingest_manager_listings(conn, str(tmp_path / "feeds"))
        derive_building_names(conn)

    out = _export(tmp_path, extra)
    for path in out.iterdir():
        assert "canary-staff" not in path.read_text(encoding="utf-8").lower(), path.name
    rec = records(out)["1 solo st"]
    (manager,) = parties(rec, "manager")
    assert [set(src) for src in manager["sources"]] == [{"type", "as_of", "url"}]


def _searches(conn):
    """1 solo st: searched twice, no filing. 2 solo st: no filing, then a filing
    found. 522 e 8th ave: no filing logged, but it has a registry owner."""
    conn.executemany(
        "INSERT INTO raw_buildings (address, pid, ingested_at) VALUES (?, ?, 'now')",
        [("1 solo st", "011-111-111"), ("2 solo st", "022-222-222")],
    )
    conn.executemany(
        "INSERT INTO raw_lotr_searches (pid, searched_on, result, note, searched_at, source_path, "
        "ingested_at) VALUES (?, ?, ?, ?, ?, 'log.csv', 'now')",
        [("011-111-111", "2026-09-30", "no_filing", "CANARY-search-note", None),
         ("011-111-111", "2026-10-06", "no_filing", None, "2026-10-06 18:23"),
         ("022-222-222", "2026-09-30", "no_filing", None, None),
         ("022-222-222", "2026-10-02", "filed", None, None),
         ("008-173-613", "2026-10-06", "no_filing", None, None)],
    )


def test_buildings_searched_without_a_filing_say_so(tmp_path):
    recs = records(_export(tmp_path, _searches))
    search = {address: rec["registry_search"] for address, rec in recs.items()}
    assert search["1 solo st"] == {"status": "no_filing", "date": "2026-10-06"}
    assert owner(recs["1 solo st"])["sources"][0]["type"] == "licence"
    assert search["2 solo st"]["status"] == "not_searched"   # a later search found a filing
    assert search["522 e 8th ave"]["status"] == "filed"      # has a registry owner
    assert search["3 nobody st"]["status"] == "not_searched"
    assert search["999 nowhere rd"]["status"] == "not_searched"


def test_search_notes_never_reach_any_artifact(tmp_path):
    out = _export(tmp_path, _searches)
    for path in out.iterdir():
        assert "CANARY-search-note" not in path.read_text(encoding="utf-8"), path.name


def test_points_carry_per_owner_pids_and_interest_holders(tmp_path):
    from tc_core.export import reconstruct_points

    conn = sqlite3.connect(":memory:")
    init_db(conn)
    pid_map = _seed(conn, tmp_path)
    conn.execute(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, type_of_interest, holder_name, "
        "data_fetch_status, ingested_at) VALUES ('008-173-613', 'ST. GEORGE ESTATES LTD.', "
        "'INTEREST_HOLDER', 'RENER, GEORGE', 'SUCCESS', 'now')"
    )
    points = reconstruct_points(conn, pid_map)
    rows = {r["address"]: r for r in points.iter_rows(named=True)}
    st_george = rows["522 e 8th ave"]
    assert st_george["registry_owner_pids"] == [{"name": "ST. GEORGE ESTATES LTD.", "pids": ["008-173-613"]}]
    assert st_george["interest_holders"] == [
        {"name": "RENER, GEORGE", "interest": "interest holder", "pids": ["008-173-613"]}
    ]
    assert rows["1 solo st"]["registry_owner_pids"] == []
    assert rows["1 solo st"]["interest_holders"] == []
    assert rows["999 nowhere rd"]["interest_holders"] == []




def _all_artifact_text(out: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in out.iterdir() if p.is_file())


CONTRACT_FILES = ("building_records.json", "networks.json", "marker_metadata.json")


def _contract_text(out: Path) -> str:
    """The v2 contract files. filter_config.json keeps "(Unknown)" as the
    display name of the missing-neighbourhood bucket — UI text, not data."""
    return "\n".join((out / name).read_text(encoding="utf-8") for name in CONTRACT_FILES)


def test_v2_never_publishes_claim_notes(tmp_path):
    out = _export(tmp_path)
    assert CANARY not in _all_artifact_text(out)


def test_v2_never_publishes_lotr_residence_or_citizenship(tmp_path):
    def extra(conn):
        conn.execute(
            "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, type_of_interest, holder_name, "
            "individual_principal_residence_city, individual_citizenship_country_codes, "
            "corporation_registered_address_line1, data_fetch_status, ingested_at) VALUES "
            "('008-173-613', 'ST. GEORGE ESTATES LTD.', 'INTEREST_HOLDER', 'RENER, GEORGE', "
            "'CANARY-CITY', 'CANARY-CC', 'CANARY-STREET', 'SUCCESS', 'now')"
        )
    out = _export(tmp_path, extra=extra)
    text = _all_artifact_text(out)
    assert "RENER, GEORGE" in text  # the name is public…
    for canary in ("CANARY-CITY", "CANARY-CC", "CANARY-STREET"):
        assert canary not in text  # …nothing else about the person is


def test_v2_research_sources_collapse_and_unconfirmed_networks_stay_out(tmp_path):
    def extra(conn):
        record_claim(conn, "Solo Rentals Ltd", "Hidden Partner Ltd", "common_owner",
                     "tenant_report", confidence="unconfirmed", source_note=CANARY)
        conn.commit()
    out = _export(tmp_path, extra=extra)
    text = _all_artifact_text(out)
    assert "tenant_report" not in text and "manual_research" not in text
    assert "Hidden Partner Ltd" not in text
    for net in networks(out).values():
        assert set(net["evidence"]) == {"registry", "city_records", "vtu_research"}


def test_v2_has_no_sentinels(tmp_path):
    out = _export(tmp_path)
    text = _contract_text(out)
    assert "(Unknown)" not in text
    assert '"unknown"' not in text
    nobody = records(out)["3 nobody st"]
    assert owner(nobody) is None and parties(nobody, "licensee") == []


def test_records_carry_every_known_pid(tmp_path):
    recs = records(_export(tmp_path))
    assert recs["522 e 8th ave"]["pids"] == ["008-173-613"]
    assert recs["1 solo st"]["pids"] == []  # no PID known for it


def test_overlay_records_take_their_owner_from_the_registry(tmp_path):
    """An SRO/co-op point that matched no building still gets its registry
    filing (139 E Cordova St: 1208149 B.C. Ltd. on title, not the SRO list's owner)."""
    def extra(conn):
        conn.executemany(
            "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, type_of_interest, holder_name, "
            "order_created_date, data_fetch_status, ingested_at) VALUES "
            "('009-999-999', 'OVERLAY OWNER LTD.', ?, ?, '2026-10-08 10:00:00', 'SUCCESS', 'now')",
            [("RB_CORPORATION", "OVERLAY OWNER LTD."), ("INTEREST_HOLDER", "DOE, JANE")],
        )
        conn.execute("UPDATE overlay_housing SET sro_owner = 'Old Name Co' WHERE addr_key = '999 nowhere rd'")
        with open(tmp_path / "pid_address_map.csv", "a", encoding="utf-8") as f:
            f.write('009999999,9,999 nowhere rd,999 nowhere rd,Mount Pleasant,"49.3,-123.15"\n')

    out = _export(tmp_path, extra)
    rec = records(out)["999 nowhere rd"]
    assert rec["origin"] == "overlay_coop"
    assert [(p["role"], p["name"]) for p in rec["parties"]] == [
        ("owner", "OVERLAY OWNER LTD."), ("interest_holder", "DOE, JANE")]
    assert owner(rec)["sources"][0] == {"type": "registry", "as_of": "2026-10-08", "url": None}
    assert rec["registry_search"]["status"] == "filed"
    assert rec["pids"] == ["009-999-999"]
    assert network(out, rec)["name"] == "OVERLAY OWNER LTD."


KIND_CANARY = "CANARY-kind-91c2"


def _kind_claims(conn):
    record_claim(conn, "GLR PROPERTIES LTD.", "trust", ENTITY_KIND, "tenant_report",
                 confidence="confirmed", source_note=KIND_CANARY, reported_by="organizer-x")
    record_claim(conn, "GLR PROPERTIES LTD.", "reit", INSTITUTIONAL, "manual_research",
                 confidence="confirmed", source_note=KIND_CANARY)
    conn.commit()


def test_classification_claim_notes_and_reporters_never_reach_any_artifact(tmp_path):
    out = _export(tmp_path, extra=_kind_claims)
    text = _all_artifact_text(out)
    assert KIND_CANARY not in text and "organizer-x" not in text


def test_claimed_kind_reaches_parties_with_a_bucketed_basis(tmp_path):
    out = _export(tmp_path, extra=_kind_claims)
    recs = records(out)
    glr = next(p for r in recs.values() for p in r["parties"] if p["name"] == "GLR PROPERTIES LTD.")
    assert (glr["kind"], glr["institutional"]) == ("trust", "reit")
    building = next(r for r in recs.values() if any(p["name"] == "GLR PROPERTIES LTD." for p in r["parties"]))
    assert "vtu_research" in building["classification"]["owner"]["basis"]
    assert "tenant_report" not in json.dumps(building)


def test_every_building_is_classified_and_networks_use_the_new_kinds(tmp_path):
    out = _export(tmp_path)
    owners = {(r["classification"]["owner"] or {}).get("value") for r in records(out).values()}
    assert "private" in owners and None in owners  # 3 nobody st: nothing known is null, not "unknown"
    assert owners <= {"government", "non_profit", "coop", "private", "mixed", None}
    kinds = {e["kind"] for n in networks(out).values() for e in n["entities"]}
    assert kinds and kinds <= {"government", "non_profit", "coop", "individual", "company",
                               "numbered_company", "trust", "partnership", None}
    assert all("assessed_value" in n["totals"] for n in networks(out).values())


def test_unknown_basis_fails_the_export():
    import pytest
    from pydantic import ValidationError

    from tc_core.contract import MarketAxis
    with pytest.raises(ValidationError):
        MarketAxis(value="market", basis=["tenant_report"], inferred=True)


def test_filter_config_summarises_portfolio_size_from_network_totals(tmp_path):
    def valued(conn):
        conn.execute("UPDATE buildings SET value_land = 1000000, value_bldg = 500000")
        conn.commit()

    out = _export(tmp_path, extra=valued)
    cfg = json.loads((out / "filter_config.json").read_text())
    metrics = cfg["building_metrics"]
    for key, attr in (("portfolio_units", "portfolio-units"), ("portfolio_value", "portfolio-value")):
        assert metrics[key]["attr"] == attr
        assert key in cfg["building_metric_order"]
    totals = [n["totals"] for n in networks(out).values()]
    assert metrics["portfolio_value"]["max"] == max(t["assessed_value"] for t in totals)
    assert metrics["portfolio_units"]["max"] == max(t["units"] for t in totals)


def test_buildings_with_no_landlord_are_not_pooled_into_one_portfolio(tmp_path):
    def nobodies(conn):
        conn.executemany(
            "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, value_land, value_bldg, "
            "created_at, updated_at) VALUES (?, ?, 49.28, -123.1, 'Mount Pleasant', 900, 5000000, 5000000, 'now', 'now')",
            [("4 nobody st", "4 nobody st"), ("5 nobody st", "5 nobody st")],
        )
        conn.commit()

    out = _export(tmp_path, extra=nobodies)
    metrics = json.loads((out / "filter_config.json").read_text())["building_metrics"]
    assert metrics["portfolio_units"]["max"] == max(n["totals"]["units"] for n in networks(out).values())
    assert records(out)["4 nobody st"]["classification"]["scale"] is None
