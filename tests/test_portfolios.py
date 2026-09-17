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

from sica_core.claims import record_claim
from sica_core.db import get_connection, init_db
from sica_core.portfolios import build_landlord_portfolios


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
