"""Building and network records (spec 2026-10-08, sections 2 and 4)."""

import pytest

from tc_core.export_contract import LandShares, build_building, build_networks, land_share


def row(**kw):
    base = dict(
        b_id=7, source="building", address="396 e 2nd ave", building_name=None, other_names=[],
        local_area="Mount Pleasant", block_id=12, lat=49.27, lon=-123.09,
        in_chinatown=False, in_village_plan=False, units=53, building_source="rental inventory",
        year_built=1978.0, value_land=18949000.0, value_bldg=534000.0, n_issues=None,
        issues_details=None, network_key="unknown", network_source=None,
        registry_owner_pids=[], registry_no_filing=None, registry_retrieved=None,
        owner_name="(Unknown)", owner_key="unknown", owner_source=None, interest_holders=[],
        licence_holder="(Unknown)", managed_by=None, managed_by_source=None, listings=[],
        is_coop=False, coop_status="", coop_ownership_model="", coop_url="",
        is_sro=False, sro_owner=None, sro_operator=None, sro_ownership_group="",
        sro_operator_group="", sro_occupancy_status="", sro_registered_rooms="",
        is_rezoning=False, rezoning_status="", rezoning_category="", rezoning_status_detail="",
        rezoning_link="",
    )
    base.update(kw)
    return base


SHARES = LandShares([0.3, 0.5, 0.79, 0.9, 0.973])


def test_land_share_and_percentile():
    assert land_share(row()) == pytest.approx(0.9726, abs=1e-4)
    assert SHARES.percentile(0.9726) == 80  # 4 of 5 strictly lower
    assert SHARES.median == 0.79


@pytest.mark.parametrize("land, bldg", [(None, 534000.0), (1000.0, None), (0.0, 0.0)])
def test_value_is_null_without_both_sides(land, bldg):
    b = build_building(row(value_land=land, value_bldg=bldg), shares=SHARES, clusters={})
    assert b.value is None


def test_value_bldg_one_is_valid():
    b = build_building(row(value_land=1000000.0, value_bldg=1.0), shares=SHARES, clusters={})
    assert b.value.building == 1


def test_types_and_nulls():
    b = build_building(row(), shares=SHARES, clusters={}).model_dump(mode="json")
    assert b["year_built"] == 1978 and isinstance(b["year_built"], int)
    assert b["units_basis"] == "inventory"
    assert b["listed_in"] == ["rental_inventory"]
    assert b["network_id"] is None
    assert b["registry_search"] == {"status": "not_searched", "date": None}
    assert b["issues"] is None and b["coop"] is None and b["sro"] is None


def test_rezoning_sro_and_coop_sections():
    b = build_building(row(
        is_rezoning=True, rezoning_status="Approved", rezoning_category="approved_market",
        rezoning_status_detail="Approved March 13, 2025", rezoning_link="https://www.shapeyourcity.ca/396-e-2-ave",
        is_sro=True, sro_registered_rooms="150", sro_occupancy_status="Open",
        sro_ownership_group="Government", sro_operator_group="N on-Profit",
        is_coop=True, coop_status="closed", coop_ownership_model="non_profit", coop_url="",
    ), shares=SHARES, clusters={})
    assert b.rezoning.status == "approved" and b.rezoning.url.endswith("396-e-2-ave")
    assert (b.sro.rooms, b.sro.occupancy, b.sro.owner_sector, b.sro.operator_sector) == (
        150, "open", "government", "non_profit")
    assert (b.coop.status, b.coop.ownership_model, b.coop.url) == ("closed", "non_profit", None)
    assert b.listed_in == ["rental_inventory", "sro_inventory", "chf_bc", "rezoning"]


def test_registry_search_states():
    filed = build_building(row(registry_owner_pids=[{"name": "A LTD.", "pids": ["1"]}],
                               owner_name="A LTD.", owner_source="registry"), shares=SHARES, clusters={})
    searched = build_building(row(registry_no_filing="2026-10-06"), shares=SHARES, clusters={})
    assert filed.registry_search.status == "filed"
    assert searched.registry_search.model_dump() == {"status": "no_filing", "date": "2026-10-06"}


def test_overlay_record_builds():
    b = build_building(row(source="overlay_sro", units=None, year_built=None, value_land=None,
                           value_bldg=None, building_source=None, local_area=None,
                           is_sro=True, sro_occupancy_status="Open"), shares=SHARES, clusters={})
    assert b.origin == "overlay_sro" and b.parties == [] and b.units_basis is None


def test_networks_totals_and_tiers():
    nets = build_networks([
        dict(network_key="net:cressey", network_name="Cressey Development Group", network_source="claims",
             network_name_source="claim", network_entities=["A", "B"], network_properties_on_title=10,
             network_evidence={"registry": 7, "vtu_research": 9}, units=43, n_issues=1),
        dict(network_key="net:cressey", network_name="Cressey Development Group", network_source="claims",
             network_name_source="claim", network_entities=["A", "B"], network_properties_on_title=10,
             network_evidence={"registry": 7, "vtu_research": 9}, units=None, n_issues=None),
        dict(network_key="feliz-enterprises-ltd", network_name="Feliz Enterprises Ltd", network_source="licence",
             network_name_source=None, network_entities=None, network_properties_on_title=None,
             network_evidence=None, units=265, n_issues=0),
        dict(network_key="unknown", network_name="(Unknown)", network_source=None,
             network_name_source=None, network_entities=None, network_properties_on_title=None,
             network_evidence=None, units=5, n_issues=0),
    ])
    assert set(nets) == {"net:cressey", "feliz-enterprises-ltd"}
    c = nets["net:cressey"]
    assert (c.tier, c.name_source, c.totals.buildings, c.totals.units, c.totals.open_issues,
            c.totals.properties_on_title) == ("confirmed", "claim", 2, 43, 1, 10)
    f = nets["feliz-enterprises-ltd"]
    assert (f.tier, f.name_source, f.entities, f.evidence.registry) == ("name_match", "default", [], 0)


def test_network_evidence_carries_city_records():
    nets = build_networks([dict(
        network_key="net:wall", network_name="Wall", network_source="claims", network_name_source=None,
        network_entities=["A", "B"], network_properties_on_title=2,
        network_evidence={"registry": 1, "city_records": 4, "vtu_research": 0}, units=10, n_issues=0,
    )])
    assert nets["net:wall"].evidence.city_records == 4
