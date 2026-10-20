"""Entity kinds from names, the registry and claims (spec 2026-10-20)."""

from __future__ import annotations

import pytest

from tc_core.metrics.sector import EntityClass, EntityClassifier, kind_from_name
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
