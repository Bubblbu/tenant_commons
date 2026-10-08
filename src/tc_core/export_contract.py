"""reconstruct_points() rows -> contract v2 records (spec 2026-10-08 §2, §4)."""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable, Mapping
from statistics import median

from .contract import (
    Building, Coop, Evidence, Issues, Network, NetworkTotals, RegistrySearch, Rezoning, Sro, Value,
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
    return None if n is None else int(round(n))


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
        return int(round(100 * bisect.bisect_left(self._sorted, share) / len(self._sorted)))

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
        local_area=_text(row.get("local_area")),
        block_id=_int(row.get("block_id")),
        lat=_coord(row.get("lat")),
        lon=_coord(row.get("lon")),
        in_chinatown=bool(row.get("in_chinatown")),
        in_village_plan=bool(row.get("in_village_plan")),
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


def build_networks(rows: Iterable[Mapping[str, object]]) -> dict[str, Network]:
    """One record per network key on the map: claims networks are
    `confirmed`; every other grouping (licence name, SRO owner, an owner on
    its own) is a `name_match`."""
    networks: dict[str, Network] = {}
    for key, rows in _group_rows(rows).items():
        first = rows[0]
        claims = first.get("network_source") == "claims"
        evidence = first.get("network_evidence") or {}
        networks[key] = Network(
            id=key,
            name=_text(first["network_name"]),
            name_source="claim" if first.get("network_name_source") == "claim" else "default",
            tier="confirmed" if claims else "name_match",
            evidence=Evidence(registry=int(evidence.get("registry", 0)),
                              vtu_research=int(evidence.get("vtu_research", 0))),
            entities=[e for e in (_text(v) for v in (first.get("network_entities") or [])) if e],
            totals=NetworkTotals(
                buildings=len(rows),
                units=sum(_int(r.get("units")) or 0 for r in rows),
                open_issues=sum(_int(r.get("n_issues")) or 0 for r in rows),
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
