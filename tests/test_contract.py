"""Export contract v2: the public allowlist (spec 2026-10-08, section 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tc_core.contract import Building, Party, RegistrySearch, Source, json_schema

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "frontend" / "src" / "contract.schema.json"


def _building(**overrides) -> dict:
    base = dict(
        id=1, origin="building", address="1 Main St", name=None, also_known_as=[], pids=[],
        local_area="Kitsilano", lat=49.2, lon=-123.1,
        areas=[], units=10, units_basis="inventory",
        year_built=1970, listed_in=["rental_inventory"], value=None, issues=None,
        parties=[], network_id=None,
        registry_search={"status": "not_searched", "date": None},
        coop=None, sro=None, rezoning=None,
    )
    base.update(overrides)
    return base


def test_valid_building_round_trips():
    b = Building(**_building())
    assert b.model_dump(mode="json")["address"] == "1 Main St"


@pytest.mark.parametrize("bad", ["(Unknown)", "unknown", "UNKNOWN", "", "   "])
def test_sentinel_strings_are_rejected(bad):
    with pytest.raises(ValidationError):
        Building(**_building(local_area=bad))
    with pytest.raises(ValidationError):
        Party(role="owner", name=bad, entity_key="x", sources=[])


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        Building(**_building(member_count=3))
    with pytest.raises(ValidationError):
        Party(role="interest_holder", name="A", entity_key="a", sources=[],
              individual_principal_residence_city="Vancouver")


def test_dates_must_be_iso():
    with pytest.raises(ValidationError):
        RegistrySearch(status="no_filing", date="Oct 6 2026")
    with pytest.raises(ValidationError):
        Source(type="registry", as_of="2026-05-28 16:10:39")


@pytest.mark.parametrize("year", [1970.5, 1970.0, "1970"])
def test_year_is_not_silently_coerced(year):
    with pytest.raises(ValidationError):
        Building(**_building(year_built=year))


def test_committed_schema_matches_models():
    expected = json.dumps(json_schema(), indent=2, sort_keys=True) + "\n"
    assert SCHEMA_FILE.read_text(encoding="utf-8") == expected, (
        "contract.schema.json is stale: run `uv run python scripts/write_contract_schema.py` "
        "then `npm run gen:types` in frontend/"
    )
