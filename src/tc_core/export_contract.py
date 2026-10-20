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
from .metrics.sector import BuildingFacts, EntityClassifier, ScaleThresholds, classify_building
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


def _facts(row: Mapping[str, object], coop: Coop | None, sro: Sro | None, listed_in: list[str]) -> BuildingFacts:
    return BuildingFacts(
        city_owned=bool(row.get("city_owned")),
        coop_model=coop.ownership_model if coop else None,
        sro_owner_sector=sro.owner_sector if sro else None,
        sro_operator_sector=sro.operator_sector if sro else None,
        on_non_market_list="non_market_list" in listed_in,
        network_buildings=_int(row.get("network_buildings_on_map")),
    )


def build_building(
    row: Mapping[str, object], *, shares: LandShares, clusters: Mapping[str, str],
    classify: EntityClassifier | None = None, thresholds: ScaleThresholds = ScaleThresholds(),
) -> Building:
    classify = classify or EntityClassifier()
    parties = build_parties(row, clusters, classify)
    listed_in, coop, sro = _listed_in(row), _coop(row), _sro(row)
    return Building(
        id=int(row["b_id"]),
        origin=row.get("source") or "building",
        address=_text(row["address"]),
        name=_text(row.get("building_name")),
        also_known_as=[n for n in (_text(v) for v in (row.get("other_names") or [])) if n],
        pids=list(row.get("pids") or []),
        local_area=_text(row.get("local_area")),
        lat=_coord(row.get("lat")),
        lon=_coord(row.get("lon")),
        areas=list(row.get("areas") or []),
        units=_int(row.get("units")),
        units_basis=_units_basis(row),
        year_built=_int(row.get("year_built")),
        listed_in=listed_in,
        value=_value(row, shares),
        issues=_issues(row),
        parties=parties,
        network_id=_text(row.get("network_key")),
        registry_search=_registry_search(row),
        coop=coop,
        sro=sro,
        rezoning=_rezoning(row),
        classification=classify_building(parties, classify, _facts(row, coop, sro, listed_in), thresholds),
    )


def _name_key(name: str) -> str:
    """Spellings differing only in punctuation or case ("1030163 B.C. LTD." /
    "1030163 BC Ltd"); stricter than export_parties.match_key, which would
    also join "Development Corp" and "Developments Ltd"."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


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
    clusters: Mapping[str, str], classify: EntityClassifier,
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
        registry = sorted(n for n in spellings if classify.in_registry(n))
        name = registry[0] if registry else sorted(spellings)[0]
        kind = classify(name).kind
        kind = None if kind == "unknown" else kind
        entities.append(NetworkEntity(
            name=name, also_named=sorted(n for n in spellings if n != name), kind=kind, buildings=owned[key],
        ))
    return sorted(entities, key=lambda e: (e.kind != "individual", -e.buildings, e.name))


def build_networks(
    rows: Iterable[Mapping[str, object]],
    clusters: Mapping[str, str] | None = None,
    classify: EntityClassifier | None = None,
) -> dict[str, Network]:
    """One record per network key on the map: claims networks are
    `confirmed`; every other grouping (licence name, SRO owner, an owner on
    its own) is a `name_match`. `clusters` is claims.resolve_entity_clusters()
    output; `classify` gives each entity its kind (metrics/sector.py)."""
    clusters, classify = clusters or {}, classify or EntityClassifier()
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
                members, clusters, classify,
            ),
            totals=NetworkTotals(
                buildings=len(members),
                units=sum(_int(r.get("units")) or 0 for r in members),
                assessed_value=_assessed_total(members),
                open_issues=sum(_int(r.get("n_issues")) or 0 for r in members),
                properties_on_title=_int(first.get("network_properties_on_title")) if claims else None,
            ),
        )
    return networks


def _assessed_total(members: list[Mapping[str, object]]) -> int | None:
    """Land + building assessed value of the network's buildings on the map;
    null when none has a value. A lower bound on the landlord's holdings."""
    values = [
        (_num(r.get("value_land")) or 0) + (_num(r.get("value_bldg")) or 0)
        for r in members
        if _num(r.get("value_land")) is not None or _num(r.get("value_bldg")) is not None
    ]
    return int(round(sum(values))) if values else None


def _group_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, list[Mapping[str, object]]]:
    groups: dict[str, list[Mapping[str, object]]] = {}
    for r in rows:
        key = _text(r.get("network_key"))
        if key:
            groups.setdefault(key, []).append(r)
    return groups
