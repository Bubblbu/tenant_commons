"""reconstruct_points() rows -> contract v2 records (spec 2026-10-08 §2, §4)."""

from __future__ import annotations

import bisect
import math
import re
from collections.abc import Iterable, Mapping
from statistics import median

from .contract import (
    Building,
    Coop,
    Evidence,
    Issues,
    Network,
    NetworkEntity,
    NetworkTotals,
    RegistrySearch,
    Rezoning,
    Sro,
    Value,
)
from .export_parties import _date, _http, _text, build_parties
from .sro_text import sector

_LISTED_IN = {
    "rental inventory": "rental_inventory",
    "non-market housing list": "non_market_list",
    "rental licence": "licence",
    "manager listing": "listing",
}


def _num(value: object) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)


def _int(value: object) -> int | None:
    n = _num(value)
    return None if n is None else round(n)


def land_share(row: Mapping[str, object]) -> float | None:
    land, bldg = _num(row.get("value_land")), _num(row.get("value_bldg"))
    if land is None or bldg is None or land + bldg <= 0:
        return None
    return land / (land + bldg)


class LandShares:
    """Every building's land share, for percentiles against the city."""

    def __init__(self, shares: list[float]):
        self._sorted = sorted(shares)

    def percentile(self, share: float) -> int:
        """Whole percent of buildings with a strictly lower land share."""
        return round(100 * bisect.bisect_left(self._sorted, share) / len(self._sorted))

    @property
    def median(self) -> float | None:
        return median(self._sorted) if self._sorted else None


def _value(row, shares: LandShares) -> Value | None:
    share = land_share(row)
    if share is None:
        return None
    return Value(land=_int(row["value_land"]), building=_int(row["value_bldg"]),
                 land_share=share, land_share_pctl=shares.percentile(share))


def _units_basis(row) -> str | None:
    if _int(row.get("units")) is None:
        return None
    if row.get("building_source") == "rental licence":
        return "sro_rooms" if row.get("is_sro") else "licence_fee"
    return "inventory"


def _listed_in(row) -> list[str]:
    out = []
    first = _LISTED_IN.get(row.get("building_source") or "")
    if first:
        out.append(first)
    for flag, source in (("is_sro", "sro_inventory"), ("is_coop", "chf_bc"), ("is_rezoning", "rezoning")):
        if row.get(flag) and source not in out:
            out.append(source)
    return out


def _lower(value: object) -> str | None:
    s = _text(value)
    return s.lower() if s else None


def _coop(row) -> Coop | None:
    if not row.get("is_coop"):
        return None
    return Coop(status=_text(row["coop_status"]), ownership_model=_text(row["coop_ownership_model"]),
                url=_http(row.get("coop_url")))


def _sro(row) -> Sro | None:
    if not row.get("is_sro"):
        return None
    rooms = _text(row.get("sro_registered_rooms"))
    return Sro(
        rooms=int(rooms) if rooms and rooms.isdigit() else None,
        occupancy=_lower(row.get("sro_occupancy_status")),
        owner_sector=sector(row.get("sro_ownership_group")),
        operator_sector=sector(row.get("sro_operator_group")),
    )


def _rezoning(row) -> Rezoning | None:
    if not row.get("is_rezoning"):
        return None
    return Rezoning(status=_lower(row["rezoning_status"]), category=_text(row["rezoning_category"]),
                    detail=_text(row.get("rezoning_status_detail")), url=_http(row.get("rezoning_link")))


def _registry_search(row) -> RegistrySearch:
    if row.get("registry_owner_pids"):
        return RegistrySearch(status="filed")
    searched = _date(row.get("registry_no_filing"))
    return RegistrySearch(status="no_filing", date=searched) if searched else RegistrySearch(status="not_searched")


def _issues(row) -> Issues | None:
    count = _int(row.get("n_issues"))
    return Issues(count=count, url=_http(row.get("issues_details"))) if count else None


def _coord(value: object) -> float | None:
    n = _num(value)
    return None if n is None else round(n, 6)


def build_building(row: Mapping[str, object], *, shares: LandShares, clusters: Mapping[str, str]) -> Building:
    return Building(
        id=int(row["b_id"]),
        origin=row.get("source") or "building",
        address=_text(row["address"]),
        name=_text(row.get("building_name")),
        also_known_as=[n for n in (_text(v) for v in (row.get("other_names") or [])) if n],
        pids=list(row.get("pids") or []),
        local_area=_text(row.get("local_area")),
        block_id=_int(row.get("block_id")),
        lat=_coord(row.get("lat")),
        lon=_coord(row.get("lon")),
        areas=list(row.get("areas") or []),
        units=_int(row.get("units")),
        units_basis=_units_basis(row),
        year_built=_int(row.get("year_built")),
        listed_in=_listed_in(row),
        value=_value(row, shares),
        issues=_issues(row),
        parties=build_parties(row, clusters),
        network_id=_text(row.get("network_key")),
        registry_search=_registry_search(row),
        coop=_coop(row),
        sro=_sro(row),
        rezoning=_rezoning(row),
    )


_COMPANY_WORDS = re.compile(
    r"\b(ltd|limited|inc|incorporated|corp|corporation|co|company|society|association|"
    r"partnership|holdings?|properties|group|foundation|trust|enterprises|ventures|"
    r"investments?|realty|developments?|management|hotel|apartments|gp)\b",
    re.IGNORECASE,
)


def _name_key(name: str) -> str:
    """Spellings differing only in punctuation or case ("1030163 B.C. LTD." /
    "1030163 BC Ltd"); stricter than export_parties.match_key, which would
    also join "Development Corp" and "Developments Ltd"."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _guess_kind(name: str) -> str:
    return "company" if _COMPANY_WORDS.search(name) or re.search(r"\d{5,}", name) else "person"


def _owner_names(row: Mapping[str, object]) -> list[str]:
    """The building's owners: on title, else its SRO-listed (joint) owners."""
    registry = row.get("registry_owner_pids") or []
    if registry:
        return [e["name"] for e in registry]
    if row.get("owner_source") == "sro_list":
        return list(row.get("sro_owners") or []) or [n for n in [_text(row.get("owner_name"))] if n]
    return []


def _network_entities(
    names: list[str], members: list[Mapping[str, object]],
    clusters: Mapping[str, str], kinds: Mapping[str, str],
) -> list[NetworkEntity]:
    groups: dict[str, list[str]] = {}
    for name in names:
        key = clusters.get(name) or _name_key(name)
        groups.setdefault(key, []).append(name)
    # A name's group, whether reached by spelling or by a same_entity claim.
    group_of = {_name_key(n): k for k, ns in groups.items() for n in ns}
    owned: dict[str, int] = dict.fromkeys(groups, 0)
    for row in members:
        for key in {group_of.get(_name_key(n)) for n in _owner_names(row)} - {None}:
            owned[key] += 1
    entities = []
    for key, spellings in groups.items():
        registry = sorted(n for n in spellings if n in kinds)
        name = registry[0] if registry else sorted(spellings)[0]
        kind = next((kinds[n] for n in registry), None) or _guess_kind(name)
        entities.append(NetworkEntity(
            name=name, also_named=sorted(n for n in spellings if n != name), kind=kind, buildings=owned[key],
        ))
    return sorted(entities, key=lambda e: (e.kind != "person", -e.buildings, e.name))


def build_networks(
    rows: Iterable[Mapping[str, object]],
    clusters: Mapping[str, str] | None = None,
    kinds: Mapping[str, str] | None = None,
) -> dict[str, Network]:
    """One record per network key on the map: claims networks are
    `confirmed`; every other grouping (licence name, SRO owner, an owner on
    its own) is a `name_match`. `clusters` is claims.resolve_entity_clusters()
    output; `kinds` maps registry names to "person"/"company"."""
    clusters, kinds = clusters or {}, kinds or {}
    networks: dict[str, Network] = {}
    for key, members in _group_rows(rows).items():
        first = members[0]
        claims = first.get("network_source") == "claims"
        evidence = first.get("network_evidence") or {}
        networks[key] = Network(
            id=key,
            name=_text(first["network_name"]),
            name_source="claim" if first.get("network_name_source") == "claim" else "default",
            tier="confirmed" if claims else "name_match",
            evidence=Evidence(registry=int(evidence.get("registry", 0)),
                              city_records=int(evidence.get("city_records", 0)),
                              vtu_research=int(evidence.get("vtu_research", 0))),
            entities=_network_entities(
                [e for e in (_text(v) for v in (first.get("network_entities") or [])) if e],
                members, clusters, kinds,
            ),
            totals=NetworkTotals(
                buildings=len(members),
                units=sum(_int(r.get("units")) or 0 for r in members),
                open_issues=sum(_int(r.get("n_issues")) or 0 for r in members),
                properties_on_title=_int(first.get("network_properties_on_title")) if claims else None,
            ),
        )
    return networks


def _group_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, list[Mapping[str, object]]]:
    groups: dict[str, list[Mapping[str, object]]] = {}
    for r in rows:
        key = _text(r.get("network_key"))
        if key:
            groups.setdefault(key, []).append(r)
    return groups
