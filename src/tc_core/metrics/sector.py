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
from collections.abc import Mapping
from dataclasses import dataclass

from ..claims import ENTITY_KIND, INSTITUTIONAL, entity_attribute_claims
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
        r"investments?|enterprises|developments?|realty|assurance|insurance|bank|reit|ulc)\b",
        re.I)),
    # "Surname, Given Names" as the registry files people.
    ("individual", re.compile(r"^[A-Za-z' -]+, [A-Za-z' .-]+$")),
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
