"""A building's plain housing facts (spec 2026-10-20, housing type).

Facts the City publishes, listed as they are with no derived categories: the
2024 rental licence type (the last year licences named the building type),
whether the building is on the City's purpose-built rental list (FOI
2024-698), its zoning district, and, for non-market housing, the City's unit
counts by clientele and the operator. Licences and non-market projects are
matched by every address a building carries (primary and secondary): about
one licence in ten sits at a building's secondary address.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from ..normalize import addr_key_from_freeform

LICENCE_TYPE_LABELS = {
    "Apartment House *Historic*": "Apartment house",
    "Rooming House *Historic*": "Rooming house",
    "Apartment House-99 Year Lease *Historic*": "Apartment house (99-year lease)",
}
_DROPPED_STATUSES = {"Cancelled", "Gone Out of Business"}
PURPOSE_BUILT_RELEASE = "2024-698"
SENIORS_SHARE = 0.8


def is_seniors(seniors_units: int, family_units: int, other_units: int) -> bool:
    """Seniors housing: at least four fifths of its units are for seniors (55+)."""
    total = seniors_units + family_units + other_units
    return total > 0 and seniors_units / total >= SENIORS_SHARE


@dataclass(frozen=True)
class NonMarket:
    family_units: int  # the City's "families": units with 2+ bedrooms
    seniors_units: int
    other_units: int  # single non-seniors
    operators: list[str]
    seniors: bool


@dataclass(frozen=True)
class HousingFacts:
    licence_types: list[str] = field(default_factory=list)
    purpose_built: bool = False
    zoning: str | None = None
    non_market: NonMarket | None = None


def _building_rows(conn: sqlite3.Connection) -> dict[int, list[tuple]]:
    rows: dict[int, list[tuple]] = defaultdict(list)
    for bid, addr_key, address, secondary, release, zoning in conn.execute(
        "SELECT b.building_id, b.addr_key, r.address, r.secondary_addresses, r.foi_release, r.zoning_district "
        "FROM buildings b LEFT JOIN json_each(b.source_row_ids) j "
        "LEFT JOIN raw_buildings r ON r.raw_building_id = j.value"
    ):
        rows[bid].append((addr_key, address, secondary, release, zoning))
    return rows


def _address_index(rows: dict[int, list[tuple]]) -> dict[str, int]:
    """Address key -> building, for every address a building carries."""
    index: dict[str, int] = {}
    for bid, rs in rows.items():
        for addr_key, address, secondary, _, _ in rs:
            keys = [addr_key, address, *((secondary or "").split(";"))]
            for k in keys:
                if k and k.strip():
                    index.setdefault(addr_key_from_freeform(k), bid)
    return index


def _licence_types(conn: sqlite3.Connection, index: dict[str, int]) -> dict[int, set[str]]:
    found: dict[int, set[str]] = defaultdict(set)
    for status, btype, house, street in conn.execute(
        "SELECT status, businesstype, house, street FROM raw_licences_2024 WHERE house IS NOT NULL"
    ):
        label = LICENCE_TYPE_LABELS.get(btype)
        bid = index.get(addr_key_from_freeform(f"{house} {street}"))
        if label and bid is not None and status not in _DROPPED_STATUSES:
            found[bid].add(label)
    return found


def _non_market(conn: sqlite3.Connection, index: dict[str, int]) -> dict[int, NonMarket]:
    units: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    operators: dict[int, list[str]] = defaultdict(list)
    for address, operator, fam, sen, oth in conn.execute(
        "SELECT address, operator, clientele_families, clientele_seniors, clientele_other "
        "FROM raw_non_market WHERE project_status = 'Completed' AND address IS NOT NULL"
    ):
        bid = index.get(addr_key_from_freeform(address))
        if bid is None:
            continue
        u = units[bid]
        u[0] += fam or 0
        u[1] += sen or 0
        u[2] += oth or 0
        if operator and operator.strip() and operator.strip() not in operators[bid]:
            operators[bid].append(operator.strip())
    return {
        bid: NonMarket(family_units=f, seniors_units=s, other_units=o, operators=operators[bid],
                       seniors=is_seniors(s, f, o))
        for bid, (f, s, o) in units.items()
    }


def housing_facts(conn: sqlite3.Connection) -> dict[int, HousingFacts]:
    """building_id -> HousingFacts for every building."""
    rows = _building_rows(conn)
    index = _address_index(rows)
    licences = _licence_types(conn, index)
    non_market = _non_market(conn, index)
    facts = {}
    for bid, rs in rows.items():
        zonings = [z for *_, z in rs if z]
        facts[bid] = HousingFacts(
            licence_types=sorted(licences.get(bid, ())),
            purpose_built=any(release == PURPOSE_BUILT_RELEASE for *_, release, _ in rs),
            zoning=zonings[0] if zonings else None,
            non_market=non_market.get(bid),
        )
    return facts
