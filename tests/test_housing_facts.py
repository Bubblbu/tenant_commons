"""A building's plain housing facts (spec 2026-10-20, housing type): its 2024
licence type, whether it is on the City's purpose-built rental list, its
zoning, and the non-market list's units by clientele and operator."""

from __future__ import annotations

from tc_core.db import get_connection, init_db
from tc_core.metrics.housing import NonMarket, housing_facts


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    conn.executemany(
        "INSERT INTO raw_buildings (raw_building_id, address, secondary_addresses, foi_release, zoning_district, "
        "ingested_at) VALUES (?, ?, ?, ?, ?, 'now')",
        [(1, "1615 robson st", "777 cardero st;1625 robson st", "2024-698", "C-5A"),
         (2, "2137 w 1st ave", None, None, "RM-4"),
         (3, "995 e 52nd ave", None, "2023-186", None)],
    )
    conn.executemany(
        "INSERT INTO buildings (building_id, addr_key, address, source_row_ids, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'now', 'now')",
        [(10, "1615 robson st", "1615 robson st", "[1]"), (11, "2137 w 1st ave", "2137 w 1st ave", "[2]"),
         (12, "995 e 52nd ave", "995 e 52nd ave", "[3]")],
    )
    conn.executemany(
        "INSERT INTO raw_licences_2024 (licencenumber, status, businesstype, house, street, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, 'now')",
        [("24-1", "Inactive", "Apartment House *Historic*", "777", "Cardero St"),
         ("24-2", "Cancelled", "Rooming House *Historic*", "1615", "ROBSON ST"),
         ("24-3", "Inactive", "Apartment House-99 Year Lease *Historic*", "2137", "W 1ST AVE")],
    )
    conn.executemany(
        "INSERT INTO raw_non_market (index_number, name, address, project_status, operator, clientele_families, "
        "clientele_seniors, clientele_other, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'now')",
        [("6", "Helen's Court Co-op", "2137 W 1st Ave", "Completed", "Helen's Court Co-op Housing Association", 35, 0, 9),
         ("7", "New Chelsea Gardens - Seniors", "995 E 52nd Ave", "Completed", "New Chelsea Society", 0, 54, 0),
         ("8", "Phase II", "995 E 52nd Ave", "Completed", "New Chelsea Society", 0, 10, 2),
         ("9", "Proposed", "1615 Robson St", "Proposed", "Some Society", 10, 0, 0)],
    )
    conn.commit()
    return conn


def test_licence_type_matches_a_secondary_address_and_skips_cancelled_licences():
    facts = housing_facts(_conn())
    assert facts[10].licence_types == ["Apartment house"]
    assert facts[11].licence_types == ["Apartment house (99-year lease)"]
    assert facts[12].licence_types == []


def test_purpose_built_list_and_zoning():
    facts = housing_facts(_conn())
    assert (facts[10].purpose_built, facts[10].zoning) == (True, "C-5A")
    assert (facts[12].purpose_built, facts[12].zoning) == (False, None)


def test_non_market_units_by_clientele_summed_across_completed_projects():
    facts = housing_facts(_conn())
    assert facts[11].non_market == NonMarket(family_units=35, seniors_units=0, other_units=9,
                                             operators=["Helen's Court Co-op Housing Association"], seniors=False)
    assert facts[12].non_market == NonMarket(family_units=0, seniors_units=64, other_units=2,
                                             operators=["New Chelsea Society"], seniors=True)
    assert facts[10].non_market is None  # only a proposed project there


def test_seniors_needs_four_fifths_of_units():
    from tc_core.metrics.housing import is_seniors
    assert is_seniors(80, 20, 0) and not is_seniors(79, 21, 0) and not is_seniors(0, 0, 0)
