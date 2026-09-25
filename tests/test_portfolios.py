"""Targeted tests for portfolios.py's claims-derived landlord clustering
join (CLAUDE.md Phase 1: "wire in claims-derived landlord clustering").

Covers the concrete case this feature exists to fix: a real landlord
disclosed on the BC Land Owner Transparency Registry under several
different-looking reporting-body names, linked by a confirmed common_owner
claim, should surface as ONE portfolio across all their buildings, keyed by
PID rather than by any older business-name label.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tc_core.claims import NETWORK_LABEL, record_claim
from tc_core.db import get_connection, init_db
from tc_core.metrics.portfolios import build_landlord_portfolios


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def _insert_raw_lotr(conn, pid: str, reporting_body_name: str) -> None:
    conn.execute(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, ingested_at) "
        "VALUES (?, ?, '2026-01-01T00:00:00+00:00')",
        (pid, reporting_body_name),
    )


def _write_pid_address_map(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = ["pid,address_point_id,address,addr_key,local_area,lat_lon"]
    for pid, addr_key in rows:
        lines.append(f"{pid},1,{addr_key},{addr_key},West End,\"49.28,-123.13\"")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_build_landlord_portfolios_joins_cluster_across_pids(tmp_path):
    conn = _conn()

    # GLR Properties Ltd. reports two PIDs directly; Rener Holdings Ltd
    # reports one more. A confirmed common_owner claim says they share a
    # real owner -- the pattern the GLR investigation surfaced.
    _insert_raw_lotr(conn, "111", "GLR PROPERTIES LTD")
    _insert_raw_lotr(conn, "222", "GLR PROPERTIES LTD")
    _insert_raw_lotr(conn, "333", "RENER HOLDINGS LTD")

    record_claim(
        conn,
        entity_a="GLR PROPERTIES LTD",
        entity_b="RENER HOLDINGS LTD",
        relationship="common_owner",
        source_type="public_registry",
        confidence="confirmed",
    )

    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(
        pid_map_path,
        [("111", "1200 alberni st"), ("222", "1210 alberni st"), ("333", "800 nicola st")],
    )

    portfolios = build_landlord_portfolios(conn, str(pid_map_path))

    assert set(portfolios) == {"1200 alberni st", "1210 alberni st", "800 nicola st"}
    names = {p.portfolio_name for p in portfolios.values()}
    assert names == {"GLR PROPERTIES LTD"}  # holds the most PIDs (2 vs 1)
    portfolio = portfolios["1200 alberni st"]
    assert portfolio.entities == ["GLR PROPERTIES LTD", "RENER HOLDINGS LTD"]
    assert len(portfolio.addr_keys) == 3


def test_build_landlord_portfolios_matches_punctuation_variant_reporting_body(tmp_path):
    conn = _conn()

    # raw_lotr_ownership is un-deduplicated source data: the same corp can
    # appear under two spellings across rows. ownership_claims only ever
    # stores one of them (record_claim()'s auto-collapse) -- the portfolio
    # join has to reach PIDs reported under BOTH spellings anyway.
    _insert_raw_lotr(conn, "111", "GLR PROPERTIES LTD")
    _insert_raw_lotr(conn, "222", "GLR PROPERTIES LTD.")

    record_claim(
        conn,
        entity_a="GLR PROPERTIES LTD",
        entity_b="RENER, LUDVIK",
        relationship="common_owner",
        source_type="public_registry",
        confidence="confirmed",
    )

    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(
        pid_map_path, [("111", "1200 alberni st"), ("222", "1210 alberni st")]
    )

    portfolios = build_landlord_portfolios(conn, str(pid_map_path))

    assert set(portfolios) == {"1200 alberni st", "1210 alberni st"}


def test_build_landlord_portfolios_normalizes_dashed_vs_undashed_pid(tmp_path):
    conn = _conn()

    # raw_lotr_ownership stores PIDs dashed; pid_address_map.csv (Vancouver
    # Open Data) stores the same PID undashed. The join must normalize both.
    _insert_raw_lotr(conn, "007-265-280", "GLR PROPERTIES LTD")
    _insert_raw_lotr(conn, "007-265-281", "RENER HOLDINGS LTD")
    record_claim(
        conn,
        entity_a="GLR PROPERTIES LTD",
        entity_b="RENER HOLDINGS LTD",
        relationship="common_owner",
        source_type="public_registry",
        confidence="confirmed",
    )

    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(
        pid_map_path, [("007265280", "1200 alberni st"), ("007265281", "1210 alberni st")]
    )

    portfolios = build_landlord_portfolios(conn, str(pid_map_path))

    assert set(portfolios) == {"1200 alberni st", "1210 alberni st"}


def test_build_landlord_portfolios_omits_unclustered_and_unmapped_buildings(tmp_path):
    conn = _conn()
    _insert_raw_lotr(conn, "111", "SOLO LANDLORD LTD")

    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(pid_map_path, [("111", "1 solo st"), ("999", "no claim here")])

    portfolios = build_landlord_portfolios(conn, str(pid_map_path))

    # No common_owner claim at all -> resolve_owner_groups() has nothing to
    # cluster, so no portfolio is produced even though the PID resolves fine.
    assert portfolios == {}


def _glr_setup(tmp_path):
    conn = _conn()
    _insert_raw_lotr(conn, "111", "GLR PROPERTIES LTD")
    _insert_raw_lotr(conn, "222", "GLR PROPERTIES LTD")
    _insert_raw_lotr(conn, "333", "RENER HOLDINGS LTD")
    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(
        pid_map_path,
        [("111", "1200 alberni st"), ("222", "1210 alberni st"), ("333", "800 nicola st")],
    )
    return conn, str(pid_map_path)


def _link(conn, a, b, source_type="public_registry", confidence="confirmed"):
    record_claim(conn, entity_a=a, entity_b=b, relationship="common_owner",
                 source_type=source_type, confidence=confidence)


def test_network_name_defaults_to_the_entity_with_most_pids(tmp_path):
    conn, pid_map = _glr_setup(tmp_path)
    _link(conn, "GLR PROPERTIES LTD", "RENER HOLDINGS LTD")
    p = build_landlord_portfolios(conn, pid_map)["800 nicola st"]
    assert (p.portfolio_name, p.name_source, p.portfolio_key) == (
        "GLR PROPERTIES LTD", "default", "glr-properties-ltd"
    )


def test_confirmed_network_label_renames_the_network_but_keeps_its_key(tmp_path):
    conn, pid_map = _glr_setup(tmp_path)
    _link(conn, "GLR PROPERTIES LTD", "RENER HOLDINGS LTD")
    record_claim(conn, "RENER HOLDINGS LTD", "Rener family", NETWORK_LABEL,
                 "manual_research", confidence="confirmed")
    p = build_landlord_portfolios(conn, pid_map)["1200 alberni st"]
    assert (p.portfolio_name, p.name_source, p.portfolio_key) == (
        "Rener family", "claim", "glr-properties-ltd"
    )


def test_unconfirmed_or_stray_labels_are_ignored(tmp_path):
    conn, pid_map = _glr_setup(tmp_path)
    _link(conn, "GLR PROPERTIES LTD", "RENER HOLDINGS LTD")
    record_claim(conn, "RENER HOLDINGS LTD", "Unconfirmed name", NETWORK_LABEL, "manual_research")
    record_claim(conn, "SOMEONE ELSE LTD", "Stray name", NETWORK_LABEL,
                 "manual_research", confidence="confirmed")
    p = build_landlord_portfolios(conn, pid_map)["1200 alberni st"]
    assert (p.portfolio_name, p.name_source) == ("GLR PROPERTIES LTD", "default")


def test_evidence_counts_collapse_non_registry_sources(tmp_path):
    conn, pid_map = _glr_setup(tmp_path)
    _link(conn, "GLR PROPERTIES LTD", "RENER HOLDINGS LTD")
    _link(conn, "GLR PROPERTIES LTD", "RENER, LUDVIK", source_type="manual_research")
    _link(conn, "RENER HOLDINGS LTD", "RENER, LUDVIK", source_type="tenant_report")
    _link(conn, "RENER HOLDINGS LTD", "RENER, ANA", source_type="manual_research",
          confidence="unconfirmed")
    p = build_landlord_portfolios(conn, pid_map)["1200 alberni st"]
    assert p.evidence == {"registry": 1, "vtu_research": 2}


def _contested(tmp_path, pids: list[tuple[str, str, str]], x_first: bool):
    """pids: (pid, reporting body, addr_key). Networks X and Y are each one
    confirmed link; x_first controls which claim is inserted first."""
    conn = _conn()
    for pid, body, _ in pids:
        _insert_raw_lotr(conn, pid, body)
    pid_map = tmp_path / f"map_{len(pids)}_{x_first}.csv"
    _write_pid_address_map(pid_map, [(pid, addr_key) for pid, _, addr_key in pids])
    links = [("X ONE LTD", "X TWO LTD"), ("Y ONE LTD", "Y TWO LTD")]
    for a, b in (links if x_first else links[::-1]):
        _link(conn, a, b)
    return build_landlord_portfolios(conn, str(pid_map))


def test_contested_building_goes_to_the_network_holding_most_of_its_pids(tmp_path):
    pids = [("1", "X ONE LTD", "5 shared st"), ("2", "X ONE LTD", "5 shared st"),
            ("3", "Y ONE LTD", "5 shared st"), ("4", "Y ONE LTD", "9 y st")]
    for x_first in (True, False):
        assert _contested(tmp_path, pids, x_first)["5 shared st"].portfolio_key == "x-one-ltd"


def test_contested_tie_goes_to_the_larger_network(tmp_path):
    pids = [("1", "X ONE LTD", "5 shared st"), ("3", "Y ONE LTD", "5 shared st"),
            ("4", "Y ONE LTD", "9 y st")]
    for x_first in (True, False):
        assert _contested(tmp_path, pids, x_first)["5 shared st"].portfolio_key == "y-one-ltd"


def _insert_raw_building(conn, address: str, pid: str) -> None:
    conn.execute(
        "INSERT INTO raw_buildings (address, pid, ingested_at) "
        "VALUES (?, ?, '2026-01-01T00:00:00+00:00')",
        (address, pid),
    )


def _cluster_glr_and_rener(conn) -> None:
    _insert_raw_lotr(conn, "111", "GLR PROPERTIES LTD")
    _insert_raw_lotr(conn, "222", "RENER HOLDINGS LTD")
    record_claim(
        conn,
        entity_a="GLR PROPERTIES LTD",
        entity_b="RENER HOLDINGS LTD",
        relationship="common_owner",
        source_type="public_registry",
        confidence="confirmed",
    )


def test_build_landlord_portfolios_reaches_building_through_its_own_pid(tmp_path):
    # 512 Campbell Ave sits on the 500 Campbell Ave parcel: the City's
    # address points (pid_address_map.csv) only know the parcel's primary
    # address, but the building record carries the PID itself.
    conn = _conn()
    _cluster_glr_and_rener(conn)
    _insert_raw_building(conn, "512 Campbell Ave", "222")

    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(
        pid_map_path, [("111", "1200 alberni st"), ("222", "500 campbell ave")]
    )

    portfolios = build_landlord_portfolios(conn, str(pid_map_path))

    assert "512 campbell ave" in portfolios
    assert portfolios["512 campbell ave"].portfolio_name == portfolios["1200 alberni st"].portfolio_name


def test_build_landlord_portfolios_reaches_every_address_point_of_a_pid(tmp_path):
    conn = _conn()
    _cluster_glr_and_rener(conn)
    _insert_raw_building(conn, "900 Multi Pid St", "111;333")

    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(
        pid_map_path,
        [("111", "1200 alberni st"), ("111", "1202 alberni st"), ("222", "800 nicola st")],
    )

    portfolios = build_landlord_portfolios(conn, str(pid_map_path))

    assert {"1200 alberni st", "1202 alberni st", "900 multi pid st"} <= set(portfolios)


def test_building_count_does_not_double_count_a_building_and_its_parcel_address(tmp_path):
    conn = _conn()
    _cluster_glr_and_rener(conn)
    _insert_raw_building(conn, "512 Campbell Ave", "222")

    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(
        pid_map_path, [("111", "1200 alberni st"), ("222", "500 campbell ave")]
    )

    portfolios = build_landlord_portfolios(conn, str(pid_map_path))

    # 1200 Alberni + 512 Campbell; 500 Campbell is 512's parcel, not a second building.
    assert portfolios["512 campbell ave"].building_count == 2


def test_building_count_keeps_two_buildings_on_one_parcel(tmp_path):
    conn = _conn()
    _cluster_glr_and_rener(conn)
    _insert_raw_building(conn, "350 Keefer St", "222")
    _insert_raw_building(conn, "705 Jackson Ave", "222")

    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(pid_map_path, [("111", "1200 alberni st"), ("222", "610 gore ave")])

    portfolios = build_landlord_portfolios(conn, str(pid_map_path))

    assert portfolios["350 keefer st"].building_count == 3


def _insert_licensed_building(conn, address: str, licensee: str, pid: str | None = None) -> None:
    conn.execute(
        "INSERT INTO raw_buildings (address, pid, bsns_name, ingested_at) "
        "VALUES (?, ?, ?, '2026-01-01T00:00:00+00:00')",
        (address, pid, licensee),
    )


def _claim(conn, a, b, relationship="common_owner", source_type="manual_research"):
    record_claim(conn, entity_a=a, entity_b=b, relationship=relationship,
                 source_type=source_type, confidence="confirmed")


def test_group_reaches_buildings_through_the_licence_holder_name(tmp_path):
    # Wolverton Group: companies linked by research claims, known only as licensees.
    conn = _conn()
    _claim(conn, "Huntly Investments Ltd", "Lord Nelson Suites Inc")
    _insert_licensed_building(conn, "1 Huntly St", "Huntly Investments Ltd")
    _insert_licensed_building(conn, "2 Nelson St", "Lord Nelson Suites Inc")
    _insert_licensed_building(conn, "3 Other St", "Unrelated Ltd")
    pid_map = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(pid_map, [])

    portfolios = build_landlord_portfolios(conn, str(pid_map))

    assert set(portfolios) == {"1 huntly st", "2 nelson st"}
    assert portfolios["1 huntly st"].building_count == 2


def test_same_entity_claims_group_spellings_of_one_company(tmp_path):
    conn = _conn()
    _claim(conn, "Hollyburn Properties Ltd", "Hollyburn Properties Limited", relationship="same_entity")
    _insert_licensed_building(conn, "1 Beach Ave", "Hollyburn Properties Limited")
    _insert_licensed_building(conn, "2 Beach Ave", "Hollyburn Properties Ltd")
    pid_map = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(pid_map, [])

    portfolios = build_landlord_portfolios(conn, str(pid_map))

    assert portfolios["1 beach ave"] is portfolios["2 beach ave"]


def test_registry_filings_outweigh_a_licence_when_two_groups_reach_a_building(tmp_path):
    conn = _conn()
    _cluster_glr_and_rener(conn)  # registry group: GLR (PID 111) ~ Rener (PID 222)
    _claim(conn, "Licensee A Ltd", "Licensee B Ltd")
    _insert_licensed_building(conn, "500 Contested St", "Licensee A Ltd", pid="222")
    _insert_licensed_building(conn, "501 Other St", "Licensee B Ltd")
    pid_map = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(pid_map, [("111", "1200 alberni st")])

    portfolios = build_landlord_portfolios(conn, str(pid_map))

    assert "RENER HOLDINGS LTD" in portfolios["500 contested st"].entities


def test_group_name_defaults_to_the_company_with_most_buildings_when_none_is_on_title(tmp_path):
    conn = _conn()
    _claim(conn, "Alpha Ltd", "Beta Ltd")
    _insert_licensed_building(conn, "1 A St", "Beta Ltd")
    _insert_licensed_building(conn, "2 A St", "Beta Ltd")
    _insert_licensed_building(conn, "3 A St", "Alpha Ltd")
    pid_map = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(pid_map, [])

    assert build_landlord_portfolios(conn, str(pid_map))["1 a st"].portfolio_name == "Beta Ltd"
