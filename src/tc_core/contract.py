"""Public export contract v2 (spec 2026-10-08-building-popup-and-contract-v2-design.md).

These models are the allowlist of what reaches the public artifacts:
`extra="forbid"` means a field reaches building_records.json/networks.json
only by being declared here, so a sensitive column can't leak by being
added to a dataframe. Missing values are null — never a sentinel string.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, Strict

SCHEMA_VERSION = 2

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
    kind: None = None  # reserved for the sector project
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


class Building(_Model):
    id: Int
    origin: Literal["building", "overlay_sro", "overlay_coop"]
    address: Text
    name: Text | None
    also_known_as: list[Text]
    # Every parcel known to carry the address, searched in the registry or not.
    pids: list[Text]
    local_area: Text | None
    block_id: Int | None
    lat: float | None
    lon: float | None
    in_chinatown: bool
    in_village_plan: bool
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


class Evidence(_Model):
    registry: Int
    vtu_research: Int


class NetworkTotals(_Model):
    buildings: Int
    units: Int
    open_issues: Int
    properties_on_title: Int | None


class Network(_Model):
    id: Text
    name: Text
    name_source: Literal["claim", "default"]
    tier: Literal["confirmed", "name_match"]
    evidence: Evidence
    entities: list[Text]
    totals: NetworkTotals


class BuildingRecordsFile(_Model):
    schema_version: Literal[2]
    records: dict[str, Building]


class NetworksFile(_Model):
    schema_version: Literal[2]
    networks: dict[str, Network]


class Contract(_Model):
    """Schema root only: one place the frontend's types are generated from."""

    building_records: BuildingRecordsFile
    networks: NetworksFile


def json_schema() -> dict:
    return Contract.model_json_schema(mode="serialization")
