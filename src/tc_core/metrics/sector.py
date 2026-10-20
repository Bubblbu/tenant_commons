"""Who owns and runs a building, by kind (spec 2026-10-20).

Entities get a kind (government / non-profit / co-op / individual / company /
numbered company / trust / partnership) from, in order: a confirmed
entity_kind claim, the registry's own individual-or-corporation record, then
name rules. Buildings get an owner type, market status, operator type and
scale from their parties plus City lists. Pure functions apart from the
loaders, so the rules are testable without a database.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from ..claims import ENTITY_KIND, INSTITUTIONAL, entity_attribute_claims
from ..contract import Classification, MarketAxis, OperatorAxis, OwnerAxis, Party
from ..normalize import sanitize_owner
from .portfolios import EVIDENCE_BUCKET

# Ordered: the first match wins. Government bodies are named outright, so
# "...Society of British Columbia" stays a society.
_NAME_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("government", re.compile(
        r"^(the )?city of vancouver\b|\bbc housing\b|british columbia housing management commission|"
        r"provincial rental housing corp|vancouver public housing corp|vancouver affordable housing agency|"
        r"\b(his|her) majesty\b|government of canada|canada mortgage and housing|"
        r"^province of british columbia$|board of parks and recreation|^school district",
        re.I)),
    ("coop", re.compile(r"\bco-?op(erative)?\b", re.I)),
    ("non_profit", re.compile(
        r"\b(society|foundation|church|parish|diocese|synod|ywca|ymca|benevolent|legion|"
        r"young (wo)?men'?s christian association)\b", re.I)),
    ("numbered_company", re.compile(r"^\d{6,}\s*b\.?\s*c\.?\s*(ltd|limited|inc|corp)", re.I)),
    ("partnership", re.compile(r"\b(limited partnership|partnership|l\.?p\.?)\s*$", re.I)),
    ("company", re.compile(r"\btrust company\b", re.I)),
    ("trust", re.compile(r"\btrust\b", re.I)),
    ("company", re.compile(
        r"\b(ltd|limited|inc|incorporated|corp|corporation|company|holdings?|properties|"
        r"investments?|enterprises|developments?|realty|assurance|insurance|bank|reit|ulc|"
        r"group|management|ventures|apartments|hotel|gp)\b",
        re.I)),
    # "Surname, Given Names" as the registry files people.
    ("individual", re.compile(r"^[A-Za-z' -]+, [A-Za-z' .-]+$")),
    # Two to four plain words and nothing company-like ("Chris Wall"): a
    # person written given-name first, as the old network kind guess had it.
    ("individual", re.compile(r"^[A-Za-z'.-]+( [A-Za-z'.-]+){1,3}$")),
]

CLAIM_BASIS = {"registry": "claim_registry", "city_records": "claim_city_records", "vtu_research": "vtu_research"}


def claim_basis(source_type: str) -> str:
    """A claim's public basis: provincial registry, City records or VTU research."""
    return CLAIM_BASIS[EVIDENCE_BUCKET.get(source_type, "vtu_research")]


def kind_from_name(name: str) -> str:
    name = (name or "").strip()
    for kind, pattern in _NAME_RULES:
        if pattern.search(name):
            return kind
    return "unknown"


@dataclass(frozen=True)
class EntityClass:
    kind: str
    basis: str  # a contract Basis value
    inferred: bool
    institutional: str | None = None


def registry_holder_types(conn: sqlite3.Connection) -> dict[str, str]:
    """{sanitize_owner(holder name): "individual" | "corporation"} from the
    registry's own record of each holder (reporting bodies included)."""
    out: dict[str, str] = {}
    for name, holder_type in conn.execute(
        "SELECT DISTINCT TRIM(holder_name), holder_type FROM raw_lotr_ownership "
        "WHERE holder_name IS NOT NULL AND TRIM(holder_name) != '' AND holder_type IS NOT NULL"
    ):
        out[sanitize_owner(name)] = "individual" if holder_type == "INDIVIDUAL" else "corporation"
    return out


class EntityClassifier:
    """name -> EntityClass. Claims beat the registry, the registry beats names."""

    def __init__(
        self,
        registry: Mapping[str, str] | None = None,
        kinds: Mapping[str, tuple[str, str]] | None = None,
        institutional: Mapping[str, tuple[str, str]] | None = None,
    ) -> None:
        self._registry = registry or {}
        self._kinds = kinds or {}
        self._institutional = institutional or {}
        self._cache: dict[str, EntityClass] = {}

    @classmethod
    def from_conn(cls, conn: sqlite3.Connection) -> EntityClassifier:
        return cls(
            registry=registry_holder_types(conn),
            kinds=entity_attribute_claims(conn, ENTITY_KIND),
            institutional=entity_attribute_claims(conn, INSTITUTIONAL),
        )

    def in_registry(self, name: str) -> bool:
        """Whether the registry has a holder by this name (any spelling noise)."""
        return sanitize_owner(name) in self._registry

    def __call__(self, name: str) -> EntityClass:
        if name not in self._cache:
            self._cache[name] = self._classify(name)
        return self._cache[name]

    def _classify(self, name: str) -> EntityClass:
        key = sanitize_owner(name)
        institutional = self._institutional.get(key, (None, None))[0]
        if key in self._kinds:
            kind, source = self._kinds[key]
            return EntityClass(kind, claim_basis(source), False, institutional)
        by_name = kind_from_name(name)
        holder = self._registry.get(key)
        if holder == "individual":
            return EntityClass("individual", "registry", False, institutional)
        if holder == "corporation" and by_name in ("individual", "unknown"):
            return EntityClass("company", "registry", False, institutional)
        return EntityClass(by_name, "name_rule", True, institutional)


OWNER_TYPE_OF_KIND = {
    "government": "government", "non_profit": "non_profit", "coop": "coop",
    "individual": "private", "company": "private", "numbered_company": "private",
    "trust": "private", "partnership": "private", "unknown": "unknown",
}
_SECTOR_OWNER_TYPE = {"private": "private", "non_profit": "non_profit",
                      "government": "government", "chinese_society": "non_profit"}


@dataclass(frozen=True)
class BuildingFacts:
    city_owned: bool = False
    coop_model: str | None = None  # Coop.ownership_model
    sro_owner_sector: str | None = None
    sro_operator_sector: str | None = None
    on_non_market_list: bool = False
    network_buildings: int | None = None


@dataclass(frozen=True)
class ScaleThresholds:
    small_portfolio_min: int = 2
    large_portfolio_min: int = 10


def scale_for(n: int | None, t: ScaleThresholds) -> str | None:
    if not n:
        return None
    if n >= t.large_portfolio_min:
        return "large_portfolio"
    return "small_portfolio" if n >= t.small_portfolio_min else "single"


def _unique(items) -> list:
    return list(dict.fromkeys(i for i in items if i))


def _owner_axis(
    parties: Sequence[Party], classify: Callable[[str], EntityClass], facts: BuildingFacts
) -> OwnerAxis | None:
    """Precedence: owners on title (claims, then registry, then names decide
    their kind), the City's land list, then the co-op, SRO and non-market
    lists and finally the licence holder, the last four marked inferred."""
    owners = [p for p in parties if p.role == "owner"]
    on_title = [p for p in owners if p.sources[0].type == "registry"]
    if on_title:
        classes = [classify(p.name) for p in on_title]
        known = [t for t in _unique(OWNER_TYPE_OF_KIND[c.kind] for c in classes) if t != "unknown"]
        forms = sorted({c.kind for c in classes if OWNER_TYPE_OF_KIND[c.kind] == "private"})
        basis = _unique(["registry", *(c.basis for c in classes)])
        if facts.city_owned and set(known) - {"government"}:
            return OwnerAxis(value="mixed", legal_forms=forms, parts=sorted({"government", *known}),
                             reason="public_land_private_leasehold",
                             basis=_unique([*basis, "city_owned"]), inferred=False)
        if len(known) > 1:
            return OwnerAxis(value="mixed", legal_forms=forms, parts=sorted(known),
                             reason="owners_differ", basis=basis, inferred=False)
        if known:
            return OwnerAxis(value=known[0], legal_forms=forms, basis=basis, inferred=False)
    if facts.city_owned:
        return OwnerAxis(value="government", basis=["city_owned"], inferred=False)
    if facts.coop_model == "non_profit":
        return OwnerAxis(value="coop", basis=["chf_bc"], inferred=True)
    sro_owner = next((p for p in owners if p.sources[0].type == "sro_inventory"), None)
    if sro_owner or facts.sro_owner_sector:
        kind = classify(sro_owner.name).kind if sro_owner else "unknown"
        value = (OWNER_TYPE_OF_KIND[kind] if kind != "unknown"
                 else _SECTOR_OWNER_TYPE.get(facts.sro_owner_sector or "", "unknown"))
        if value != "unknown":
            forms = [kind] if value == "private" and kind != "unknown" else []
            return OwnerAxis(value=value, legal_forms=forms, basis=["sro_inventory"], inferred=True)
    if facts.on_non_market_list:
        operator = next((p for p in parties if p.role in ("manager", "licensee")), None)
        value = OWNER_TYPE_OF_KIND[classify(operator.name).kind] if operator else "unknown"
        if value in ("non_profit", "coop", "government"):
            return OwnerAxis(value=value, basis=["non_market_list"], inferred=True)
    licensed = next((p for p in owners if p.sources[0].type == "licence"), None) or next(
        (p for p in parties if p.role == "licensee"), None)
    if licensed:
        c = classify(licensed.name)
        value = OWNER_TYPE_OF_KIND[c.kind]
        if value != "unknown":
            forms = [c.kind] if value == "private" else []
            return OwnerAxis(value=value, legal_forms=forms, basis=_unique(["licence", c.basis]), inferred=True)
    return None


def _market_axis(owner: OwnerAxis | None, facts: BuildingFacts) -> MarketAxis | None:
    if facts.on_non_market_list:
        return MarketAxis(value="non_market", basis=["non_market_list"], inferred=False)
    if facts.coop_model == "non_profit":
        return MarketAxis(value="non_market", basis=["chf_bc"], inferred=False)
    if owner and owner.value == "government" and not owner.inferred:
        return MarketAxis(value="non_market", basis=owner.basis, inferred=False)
    if {facts.sro_owner_sector, facts.sro_operator_sector} & {"non_profit", "government"}:
        return MarketAxis(value="non_market", basis=["sro_inventory"], inferred=True)
    if facts.coop_model == "equity":
        return MarketAxis(value="market", basis=["chf_bc"], inferred=True)
    if owner and owner.value == "private":
        return MarketAxis(value="market", basis=owner.basis, inferred=True)
    return None


def _operator_axis(parties: Sequence[Party], classify: Callable[[str], EntityClass]) -> OperatorAxis | None:
    """The manager, else a licence holder who is neither owner nor manager."""
    operator = next((p for p in parties if p.role == "manager"), None) or next(
        (p for p in parties if p.role == "licensee" and p.same_as is None), None)
    if operator is None:
        return None
    value = OWNER_TYPE_OF_KIND[classify(operator.name).kind]
    if value == "unknown":
        return None
    return OperatorAxis(value=value, basis=_unique(s.type for s in operator.sources))


def classify_building(
    parties: Sequence[Party],
    classify: Callable[[str], EntityClass],
    facts: BuildingFacts,
    thresholds: ScaleThresholds = ScaleThresholds(),
) -> Classification:
    owner = _owner_axis(parties, classify, facts)
    return Classification(
        owner=owner,
        market=_market_axis(owner, facts),
        operator=_operator_axis(parties, classify),
        scale=scale_for(facts.network_buildings, thresholds),
    )


def city_owned_buildings(conn: sqlite3.Connection) -> set[int]:
    """building_ids with a folio on City land: a folio's first 8 digits are
    its land coordinate, the key of the City-owned properties list."""
    coords = {r[0] for r in conn.execute(
        "SELECT land_coord FROM raw_city_owned_properties WHERE land_coord IS NOT NULL")}
    found: set[int] = set()
    for building_id, folios in conn.execute(
        "SELECT b.building_id, r.folio FROM buildings b, json_each(b.source_row_ids) j "
        "JOIN raw_buildings r ON r.raw_building_id = j.value WHERE r.folio IS NOT NULL"
    ):
        if any(f.strip()[:8] in coords for f in folios.split(";")):
            found.add(building_id)
    return found
