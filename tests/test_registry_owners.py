"""Per-building registered owners from the BC Land Owner Transparency
Registry (spec 2026-09-23-ownership-layers-design.md §3)."""

from __future__ import annotations

from tc_core.db import get_connection, init_db
from tc_core.metrics.registry_owners import build_interest_holders, build_registry_owners


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


def test_a_strata_lot_filing_reaches_the_building_carrying_its_plan(tmp_path):
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_buildings (address, pid, ingested_at) VALUES ('958 Bute St', 'VAS684', 'now')")
    conn.execute("INSERT INTO strata_lot_pids (pid, strata_plan) VALUES ('004-525-213', 'VAS684')")
    _lotr(conn, "004-525-213", "STRATA OWNER LTD.")
    _lotr(conn, "009-999-999", "OTHER LTD.")  # a lot not in the map reaches nothing
    owners = build_registry_owners(conn, _pid_map(tmp_path, []))
    assert list(owners) == ["958 bute st"]
    assert owners["958 bute st"].owners == ["STRATA OWNER LTD."]


def test_a_strata_lot_filing_reaches_a_building_whose_address_point_carries_the_plan(tmp_path):
    # 1120 Pacific St (Whitehouse) comes from a landlord listing: no raw_buildings
    # row carries VAS267, but the City's address point does.
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_addresses (civic_number, std_street, site_id, ingested_at) "
        "VALUES ('1120.0', 'PACIFIC ST', 'VAS267', 'now')")
    conn.execute("INSERT INTO strata_lot_pids (pid, strata_plan) VALUES ('003-786-901', 'VAS267')")
    _lotr(conn, "003-786-901", "1136 PROPERTIES LTD.")
    owners = build_registry_owners(conn, _pid_map(tmp_path, []))
    assert owners["1120 pacific st"].owners == ["1136 PROPERTIES LTD."]


def _lotr_typed(conn, rows):
    """Rows of (pid, reporting body, type_of_interest, holder); every row also
    carries a residence city that must never surface."""
    conn.executemany(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, type_of_interest, holder_name, "
        "individual_principal_residence_city, order_created_date, data_fetch_status, ingested_at) "
        "VALUES (?, ?, ?, ?, 'Secret City', '2026-05-28 16:10:39', 'SUCCESS', 'now')",
        rows,
    )


def test_owner_pids_separate_joint_from_per_parcel_owners(tmp_path):
    conn = _conn()
    _lotr_typed(conn, [
        ("011-111-111", "A HOLDINGS LTD.", "RB_CORPORATION", "A HOLDINGS LTD."),
        ("011-111-111", "B HOLDINGS LTD.", "RB_CORPORATION", "B HOLDINGS LTD."),
        ("022-222-222", "B HOLDINGS LTD.", "RB_CORPORATION", "B HOLDINGS LTD."),
    ])
    pid_map = _pid_map(tmp_path, [("011111111", "1 main st"), ("022222222", "1 main st")])
    reg = build_registry_owners(conn, pid_map)["1 main st"]
    assert reg.owner_pids == {
        "B HOLDINGS LTD.": ["011-111-111", "022-222-222"],
        "A HOLDINGS LTD.": ["011-111-111"],
    }


def test_interest_holders_typed_and_reporting_bodies_excluded(tmp_path):
    conn = _conn()
    _lotr_typed(conn, [
        ("011-111-111", "EZELIYA HOLDINGS INC.", "RB_CORPORATION", "EZELIYA HOLDINGS INC."),
        ("011-111-111", "EZELIYA HOLDINGS INC.", "INTEREST_HOLDER", "KARA, JAMIL"),
        ("011-111-111", "Wong, Allen", "RB_TRUSTEE_INDIVIDUAL", "Wong, Allen"),
        ("011-111-111", "VALLEJO COURT LTD.", "RB_TRUST_SETTLOR_CORPORATION", "VALLEJO COURT LIMITED PARTNERSHIP"),
        ("011-111-111", "X LTD.", "INTEREST_HOLDER", None),
    ])
    pid_map = _pid_map(tmp_path, [("011111111", "1 main st")])
    holders = build_interest_holders(conn, pid_map)["1 main st"]
    assert holders == [
        {"name": "KARA, JAMIL", "interest": "interest holder", "pids": ["011-111-111"]},
        {"name": "VALLEJO COURT LIMITED PARTNERSHIP", "interest": "settlor", "pids": ["011-111-111"]},
    ]
    assert "Secret City" not in repr(holders)


def test_withheld_names_are_never_published_even_if_a_name_is_present(tmp_path):
    """LOTR s. 30(4) withholds some identities; a name field filled in anyway
    (e.g. from partial name parts) must still not surface."""
    conn = _conn()
    conn.executemany(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, type_of_interest, holder_name, "
        "individual_is_full_name_omitted, obscure_message, data_fetch_status, ingested_at) "
        "VALUES ('011-111-111', 'A LTD.', 'INTEREST_HOLDER', ?, ?, ?, 'SUCCESS', 'now')",
        [("WITHHELD, PERSON", "1", None),
         ("OBSCURED, PERSON", "0", "Information unavailable under s. 30(4)"),
         ("PUBLIC, PERSON", "0", None)],
    )
    holders = build_interest_holders(conn, _pid_map(tmp_path, [("011111111", "1 main st")]))
    assert [h["name"] for h in holders["1 main st"]] == ["PUBLIC, PERSON"]


def test_building_pids_come_from_every_address_point_and_are_dashed(tmp_path):
    from tc_core.metrics.registry_owners import building_pids

    conn = _conn()
    pid_map = _pid_map(tmp_path, [("004410785", "139 e cordova st"), ("4410786", "139 e cordova st"),
                                  ("011111111", "1 main st")])
    assert building_pids(conn, pid_map) == {
        "139 e cordova st": ["004-410-785", "004-410-786"],
        "1 main st": ["011-111-111"],
    }


def test_holder_types_come_from_the_registry():
    from tc_core.metrics.sector import registry_holder_types
    from tc_core.normalize import sanitize_owner

    conn = _conn()
    conn.executemany(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, type_of_interest, holder_type, holder_name, "
        "data_fetch_status, ingested_at) VALUES ('1', ?, ?, ?, ?, 'SUCCESS', 'now')",
        [("A LTD.", "RB_CORPORATION", "CORPORATION", "A LTD."),
         ("A LTD.", "INTEREST_HOLDER", "INDIVIDUAL", "DOE, JANE"),
         ("Wong, Allen", "RB_TRUSTEE_INDIVIDUAL", "INDIVIDUAL", "Wong, Allen")],
    )
    assert registry_holder_types(conn) == {
        sanitize_owner("A LTD."): "corporation", sanitize_owner("DOE, JANE"): "individual",
        sanitize_owner("Wong, Allen"): "individual",
    }
