"""Entity kinds from names, the registry and claims; building owner type,
market status, operator and scale from parties and City lists (spec 2026-10-20)."""

from __future__ import annotations

import pytest

from tc_core.contract import Party, Source
from tc_core.metrics.sector import (
    BuildingFacts,
    EntityClass,
    EntityClassifier,
    ScaleThresholds,
    classify_building,
    kind_from_name,
    scale_for,
)
from tc_core.normalize import sanitize_owner


@pytest.mark.parametrize("name, kind", [
    ("City of Vancouver", "government"),
    ("BC Housing", "government"),
    ("Provincial Rental Housing Corporation", "government"),
    ("Vancouver Public Housing Corp", "government"),
    ("Mennonite Senior Citizens Society of British Columbia", "non_profit"),
    ("YWCA BRITISH COLUMBIA", "non_profit"),
    ("Young Women's Christian Association", "non_profit"),
    ("CLT 0005 COMMUNITY SOCIETY", "non_profit"),
    ("Helen's Court Co-op Housing Association", "coop"),
    ("0888189 B.C. Ltd.", "numbered_company"),
    ("372328 BC Ltd", "numbered_company"),
    ("1566283 B.C. LTD.", "numbered_company"),
    ("Sun Life Assurance Company of Canada", "company"),
    ("bcIMC Realty Corporation", "company"),
    ("5908 Holdings Ltd.", "company"),
    ("Rei-Mar Investments Ltd & Manytree Holdings Ltd", "company"),
    ("Westbank Limited Partnership", "partnership"),
    ("Kerrisdale Family Trust", "trust"),
    ("Computershare Trust Company of Canada", "company"),
    ("Moore, Kathleen Frances", "individual"),
    ("George Rener & Alenka Rener", "unknown"),
    ("", "unknown"),
])
def test_kind_from_name(name, kind):
    assert kind_from_name(name) == kind


def test_registry_individual_is_evidence_not_inference():
    c = EntityClassifier(registry={sanitize_owner("Paul Y Mansion"): "individual"})
    assert c("Paul Y Mansion") == EntityClass(kind="individual", basis="registry", inferred=False)


def test_registry_corporation_never_becomes_an_individual():
    c = EntityClassifier(registry={sanitize_owner("Smith, John"): "corporation"})
    assert c("Smith, John").kind == "company"


def test_name_rule_is_inferred():
    assert EntityClassifier()("0792203 BC Ltd") == EntityClass(
        kind="numbered_company", basis="name_rule", inferred=True
    )


def test_claim_overrides_name_rule_and_basis_is_bucketed():
    key = sanitize_owner("Mennonite Senior Citizens Society of British Columbia")
    c = EntityClassifier(kinds={key: ("non_profit", "tenant_report")},
                         institutional={key: ("other", "public_registry")})
    got = c("Mennonite Senior Citizens Society of British Columbia")
    assert (got.kind, got.basis, got.inferred, got.institutional) == ("non_profit", "vtu_research", False, "other")


def _p(role, name, source, **kw):
    return Party(role=role, name=name, entity_key=sanitize_owner(name), sources=[Source(type=source)], **kw)


CLASSIFY = EntityClassifier()


def test_registry_numbered_company_is_private_market_inferred():
    c = classify_building([_p("owner", "0792203 BC Ltd", "registry")], CLASSIFY, BuildingFacts())
    assert c.owner.value == "private" and c.owner.legal_forms == ["numbered_company"]
    assert c.owner.inferred is False and c.owner.basis == ["registry", "name_rule"]
    assert (c.market.value, c.market.inferred) == ("market", True)


def test_owners_of_different_types_are_mixed():
    parties = [_p("owner", "New Chelsea Society", "registry"), _p("owner", "0792203 BC Ltd", "registry")]
    c = classify_building(parties, CLASSIFY, BuildingFacts())
    assert (c.owner.value, c.owner.reason) == ("mixed", "owners_differ")
    assert c.owner.parts == ["non_profit", "private"] and c.owner.legal_forms == ["numbered_company"]


def test_city_land_under_private_leasehold_is_mixed():
    c = classify_building([_p("owner", "VLC Leaseholds Ltd", "registry")], CLASSIFY, BuildingFacts(city_owned=True))
    assert (c.owner.value, c.owner.reason) == ("mixed", "public_land_private_leasehold")
    assert c.owner.parts == ["government", "private"] and "city_owned" in c.owner.basis


def test_city_owned_without_registry_owner_is_government_non_market():
    c = classify_building([], CLASSIFY, BuildingFacts(city_owned=True))
    assert (c.owner.value, c.owner.inferred, c.owner.basis) == ("government", False, ["city_owned"])
    assert (c.market.value, c.market.inferred) == ("non_market", False)


def test_licence_only_owner_is_inferred():
    parties = [_p("owner", "Willow Lane Apartments Inc", "licence"),
               _p("licensee", "Willow Lane Apartments Inc", "licence", same_as="owner")]
    c = classify_building(parties, CLASSIFY, BuildingFacts())
    assert (c.owner.value, c.owner.inferred, c.owner.basis) == ("private", True, ["licence", "name_rule"])


def test_non_profit_coop_is_coop_and_non_market():
    c = classify_building([], CLASSIFY, BuildingFacts(coop_model="non_profit"))
    assert (c.owner.value, c.owner.inferred) == ("coop", True)
    assert (c.market.value, c.market.inferred, c.market.basis) == ("non_market", False, ["chf_bc"])


def test_equity_coop_is_market_inferred():
    c = classify_building([], CLASSIFY, BuildingFacts(coop_model="equity"))
    assert (c.market.value, c.market.inferred) == ("market", True)


def test_non_market_list_beats_private_owner_for_market():
    c = classify_building([_p("owner", "0792203 BC Ltd", "registry")], CLASSIFY,
                          BuildingFacts(on_non_market_list=True))
    assert (c.market.value, c.market.inferred, c.market.basis) == ("non_market", False, ["non_market_list"])


def test_sro_with_non_profit_operator_is_non_market_inferred():
    c = classify_building([_p("owner", "Hotel Holdings Ltd", "sro_inventory")], CLASSIFY,
                          BuildingFacts(sro_owner_sector="private", sro_operator_sector="non_profit"))
    assert (c.owner.value, c.owner.inferred) == ("private", True)
    assert (c.market.value, c.market.inferred, c.market.basis) == ("non_market", True, ["sro_inventory"])


def test_operator_from_manager_then_unlinked_licensee():
    parties = [_p("owner", "0792203 BC Ltd", "registry"), _p("manager", "Atira Women's Resource Society", "listing")]
    assert classify_building(parties, CLASSIFY, BuildingFacts()).operator.value == "non_profit"
    parties = [_p("owner", "0792203 BC Ltd", "registry"),
               _p("licensee", "Urban Vision Housing Society", "licence")]
    op = classify_building(parties, CLASSIFY, BuildingFacts()).operator
    assert (op.value, op.basis) == ("non_profit", ["licence"])


def test_nothing_known_is_unknown():
    c = classify_building([], CLASSIFY, BuildingFacts())
    assert (c.owner.value, c.market.value, c.operator, c.scale) == ("unknown", "unknown", None, None)
    assert c.owner.basis == [] and c.market.basis == []


@pytest.mark.parametrize("n, scale", [(None, None), (1, "single"), (2, "small_portfolio"),
                                      (9, "small_portfolio"), (10, "large_portfolio")])
def test_scale_thresholds(n, scale):
    assert scale_for(n, ScaleThresholds()) == scale
