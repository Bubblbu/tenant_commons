"""Each building's parties in their roles (spec 2026-10-08 §3).

Reads one reconstruct_points() row. Owners come from the registry, else the
SRO inventory or licence (already resolved into owner_* by export.py);
managers from listings, licence-held management and the SRO operator; the
licensee is always listed and linked (`same_as`) to the owner or manager it
turns out to be.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from urllib.parse import urlparse

from .contract import Party, Source
from .normalize import sanitize_owner

_SUFFIXES = {"ltd", "limited", "inc", "incorporated", "corp", "corporation", "co", "company", "the"}
_OWNER_SOURCE = {"licence": "licence", "sro_list": "sro_inventory"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_SENTINELS = {"(unknown)", "unknown"}


def _text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    s = str(value).strip()
    return None if not s or s.lower() in _SENTINELS else s


def _date(value: object) -> str | None:
    s = _text(value)
    return s[:10] if s and _ISO_DATE.match(s) else None


def _http(value: object) -> str | None:
    s = _text(value)
    return s if s and urlparse(s).scheme in ("http", "https") else None


def match_key(name: str) -> str:
    """Spelling-insensitive identity of an entity name: words without
    punctuation, corporate suffixes or a plural s ("Apts. Ltd." == "Apt Ltd")."""
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in _SUFFIXES]
    return "".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words)


def _same(a: str, b: str, clusters: Mapping[str, str]) -> bool:
    if match_key(a) == match_key(b):
        return True
    ca, cb = clusters.get(a), clusters.get(b)
    return ca is not None and ca == cb


def _party(role: str, name: str, sources: list[Source], **kw) -> Party:
    return Party(role=role, name=name, entity_key=sanitize_owner(name), sources=sources, **kw)


def _owners(row: Mapping[str, object]) -> list[Party]:
    registry = row.get("registry_owner_pids") or []
    if registry:
        as_of = _date(row.get("registry_retrieved"))
        return [
            _party("owner", e["name"], [Source(type="registry", as_of=as_of)], pids=list(e["pids"]))
            for e in registry
        ]
    name = _text(row.get("owner_name"))
    source = _OWNER_SOURCE.get(_text(row.get("owner_source")) or "")
    return [_party("owner", name, [Source(type=source)])] if name and source else []


def _managers(row: Mapping[str, object], clusters: Mapping[str, str]) -> list[Party]:
    found: list[tuple[str, list[Source]]] = []

    def add(name: str | None, source: Source) -> None:
        if not name:
            return
        for known, sources in found:
            if _same(known, name, clusters):
                sources.append(source)
                return
        found.append((name, [source]))

    if _text(row.get("managed_by_source")) == "licence":
        add(_text(row.get("managed_by")), Source(type="licence"))
    listings = row.get("listings") or []
    managed = _text(row.get("managed_by"))
    # The known manager's own listing first, then any other company's.
    for listing in sorted(listings, key=lambda l: not (managed and _same(l["by"], managed, clusters))):
        add(_text(listing.get("by")), Source(
            type="listing", as_of=_date(listing.get("seen")), url=_http(listing.get("url"))
        ))
    add(_text(row.get("sro_operator")), Source(type="sro_inventory"))
    return [_party("manager", name, sources) for name, sources in found]


def build_parties(row: Mapping[str, object], clusters: Mapping[str, str]) -> list[Party]:
    owners = _owners(row)
    holders = [
        _party("interest_holder", h["name"], [Source(type="registry", as_of=_date(row.get("registry_retrieved")))],
               interest=h["interest"], pids=list(h["pids"]))
        for h in (row.get("interest_holders") or [])
    ]
    managers = _managers(row, clusters)
    parties = [*owners, *holders, *managers]
    licence = _text(row.get("licence_holder"))
    if licence:
        same_as = None
        for role, group in (("owner", owners), ("manager", managers)):
            match = next((p for p in group if _same(p.name, licence, clusters)), None)
            if match:
                same_as = role
                if not any(s.type == "licence" for s in match.sources):
                    match.sources.append(Source(type="licence"))
                break
        parties.append(_party("licensee", licence, [Source(type="licence")], same_as=same_as))
    return parties
