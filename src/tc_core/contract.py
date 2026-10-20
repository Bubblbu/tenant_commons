"""Public export contract v2 (spec 2026-10-08-building-popup-and-contract-v2-design.md).

These models are the allowlist of what reaches the public artifacts:
`extra="forbid"` means a field reaches building_records.json/networks.json
only by being declared here, so a sensitive column can't leak by being
added to a dataframe. Missing values are null — never a sentinel string.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, Strict

SCHEMA_VERSION = 5

_SENTINELS = {"(unknown)", "unknown"}


def _no_sentinel(value: str) -> str:
    if not value.strip() or value.strip().lower() in _SENTINELS:
        raise ValueError(f"missing values are null, not {value!r}")
    return value


Text = Annotated[str, AfterValidator(_no_sentinel)]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
# Strict: a float year (1970.0) or a numeric string fails instead of being coerced.
Int = Annotated[int, Strict()]

SourceType = Literal[
    "registry", "licence", "sro_inventory", "listing", "claim_registry", "vtu_research",
    "rental_inventory", "non_market_list", "chf_bc", "rezoning",
]
Role = Literal["owner", "interest_holder", "manager", "licensee"]
Sector = Literal["private", "non_profit", "government", "chinese_society"]
# Not known is null, never "unknown" (no sentinels, see module docstring).
Kind = Literal[
    "government", "non_profit", "coop", "individual", "company",
    "numbered_company", "trust", "partnership",
]
Institutional = Literal["reit", "pension_fund", "insurer", "asset_manager", "other"]
OwnerType = Literal["government", "non_profit", "coop", "private", "mixed"]
# Where a classification came from. Claims show only as their bucket.
Basis = Literal[
    "name_rule", "registry", "licence", "listing", "city_owned", "non_market_list",
    "chf_bc", "sro_inventory", "claim_registry", "claim_city_records", "vtu_research",
]
Scale = Literal["single", "small_portfolio", "large_portfolio"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class Source(_Model):
    type: SourceType
    as_of: IsoDate | None = None
    url: Text | None = None


class Party(_Model):
    role: Role
    name: Text
    entity_key: Text
    kind: Kind | None = None
    institutional: Institutional | None = None
    interest: Text | None = None
    pids: list[Text] = []
    same_as: Literal["owner", "manager"] | None = None
    sources: list[Source]


class Value(_Model):
    land: Int
    building: Int
    land_share: float = Field(ge=0, le=1)
    land_share_pctl: Int = Field(ge=0, le=100)


class Issues(_Model):
    count: Int = Field(ge=1)
    url: Text | None = None


class RegistrySearch(_Model):
    status: Literal["filed", "no_filing", "not_searched"]
    date: IsoDate | None = None


class Coop(_Model):
    status: Literal["open_waitlist", "closed"] | None = None
    ownership_model: Literal["non_profit", "equity"] | None = None
    url: Text | None = None


class Sro(_Model):
    rooms: Int | None = None
    occupancy: Literal["open", "closed"] | None = None
    owner_sector: Sector | None = None
    operator_sector: Sector | None = None


class Rezoning(_Model):
    status: Literal["approved", "rezoning", "upcoming"]
    category: Text
    detail: Text | None = None
    url: Text | None = None



class OwnerAxis(_Model):
    value: OwnerType
    legal_forms: list[Kind] = []  # the private owners' kinds
    parts: list[OwnerType] = []  # when mixed
    reason: Literal["owners_differ", "public_land_private_leasehold"] | None = None
    basis: list[Basis]
    # True when the owner is not confirmed on title, a claim or the City's
    # own land list (licence holder, SRO inventory, co-op or non-market list).
    inferred: bool


class MarketAxis(_Model):
    value: Literal["non_market", "market"]
    basis: list[Basis]
    inferred: bool


class OperatorAxis(_Model):
    value: OwnerType
    basis: list[Basis]


class Classification(_Model):
    """Each axis is null when nothing is known about it."""

    owner: OwnerAxis | None
    market: MarketAxis | None
    operator: OperatorAxis | None
    scale: Scale | None

class Building(_Model):
    id: Int
    origin: Literal["building", "overlay_sro", "overlay_coop"]
    address: Text
    name: Text | None
    also_known_as: list[Text]
    # Every parcel known to carry the address, searched in the registry or not.
    pids: list[Text]
    local_area: Text | None
    lat: float | None
    lon: float | None
    # Keys of the overlay areas (config.toml's [[overlay_areas]]) the
    # building is in, e.g. ["chinatown"]; filter_config's special_areas names them.
    areas: list[Text]
    units: Int | None
    units_basis: Literal["inventory", "licence_fee", "sro_rooms"] | None
    year_built: Int | None
    listed_in: list[SourceType]
    value: Value | None
    issues: Issues | None
    parties: list[Party]
    network_id: Text | None
    registry_search: RegistrySearch
    coop: Coop | None
    sro: Sro | None
    rezoning: Rezoning | None
    classification: Classification


class Evidence(_Model):
    """Confirmed claims linking the network, by public source category:
    provincial registry filings, City records (e.g. the SRO inventory naming
    the person behind a company), and VTU research (everything else)."""

    registry: Int
    city_records: Int
    vtu_research: Int


class NetworkTotals(_Model):
    buildings: Int
    units: Int
    # Land + building assessed value of its buildings on the map: a lower
    # bound on the landlord's holdings. Null when none has a value.
    assessed_value: Int | None
    open_issues: Int
    properties_on_title: Int | None


class NetworkEntity(_Model):
    """One entity in a network: spellings that differ only in punctuation or
    case, or that a confirmed same_entity claim links, are one entity."""

    name: Text  # the registry's spelling where there is one
    also_named: list[Text]
    kind: Kind | None
    buildings: Int  # buildings on the map it owns (on title, jointly, or per the SRO inventory)


class Network(_Model):
    id: Text
    name: Text
    name_source: Literal["claim", "default"]
    tier: Literal["confirmed", "name_match"]
    evidence: Evidence
    entities: list[NetworkEntity]
    totals: NetworkTotals


class BuildingRecordsFile(_Model):
    schema_version: Literal[5]
    records: dict[str, Building]


class NetworksFile(_Model):
    schema_version: Literal[5]
    networks: dict[str, Network]


class Contract(_Model):
    """Schema root only: one place the frontend's types are generated from."""

    building_records: BuildingRecordsFile
    networks: NetworksFile


def json_schema() -> dict:
    return Contract.model_json_schema(mode="serialization")
