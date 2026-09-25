"""Join claims-derived landlord portfolios onto buildings, via PID.

CLAUDE.md Phase 1: "Wire in claims-derived landlord clustering (grouping
shell companies under a real owner where confirmed)." The join deliberately
does NOT go through buildings' own owner_group/bsns_group label — that's a
separate, older vhd business-name classification that often splits one real
landlord across several different-looking labels (see the GLR Properties
case: the same beneficial owner shows up as "Rener Holdings Ltd", "Kruthaups
Holding Ltd", etc.) — exactly the gap this feature exists to close, so
matching against that label can't be the join key.

Instead the join goes through PID: raw_lotr_ownership already records which
PIDs each reporting corporation discloses an interest in, and
pid_address_map.csv plus the PIDs on each building record (raw_buildings.pid)
bridge PID -> addr_key. So a resolve_owner_groups()
cluster's full building footprint can be computed independent of any older
business-name label.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass, field

from ..claims import resolve_owner_groups
from ..normalize import addr_key_from_freeform, sanitize_owner


def _normalize_pid(pid: str) -> str:
    """Strip PID formatting down to bare digits.

    raw_lotr_ownership stores PIDs dashed ("007-265-280"); pid_address_map.csv
    (sourced from Vancouver Open Data) stores the same PID as a plain 9-digit
    string ("007265280"). Without normalizing both sides, the join silently
    matches nothing.
    """
    return re.sub(r"\D", "", pid or "")


@dataclass
class Portfolio:
    portfolio_key: str
    # Display name for the whole cluster: the entity holding the most PIDs
    # (ties broken alphabetically) — kept stable across every building in the
    # portfolio, rather than naming it after whichever entity happens to be
    # the direct reporting body for one particular address. Individual
    # buildings still show their own real reporting body name separately;
    # this is only the portfolio-level label.
    portfolio_name: str
    entities: list[str]
    addr_keys: set[str] = field(default_factory=set)
    # Buildings reached, not addresses: a building record and its parcel's
    # own address point (512 and 500 Campbell Ave) count once.
    building_count: int = 0


def _load_pid_to_addr_keys(path: str) -> dict[str, set[str]]:
    """{pid: {addr_key, ...}}: a PID with several address points reaches all of them."""
    mapping: dict[str, set[str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid = _normalize_pid(row.get("pid") or "")
            addr_key = (row.get("addr_key") or "").strip()
            if pid and addr_key:
                mapping.setdefault(pid, set()).add(addr_key)
    return mapping


def _building_pids(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """{pid: {addr_key, ...}} from the PIDs each building record carries.

    The City's address points only know a parcel's primary address, so a
    building listed at another address on the same parcel (512 Campbell Ave
    on the 500 Campbell Ave parcel) is unreachable through
    pid_address_map.csv alone. raw_buildings.pid is semicolon-joined, and
    addr_key is derived from the address the same way ingest/merge.py does.
    """
    rows = conn.execute(
        "SELECT address, pid FROM raw_buildings WHERE address IS NOT NULL AND pid IS NOT NULL"
    ).fetchall()
    mapping: dict[str, set[str]] = {}
    for address, pids in rows:
        addr_key = addr_key_from_freeform(address)
        if not addr_key:
            continue
        for pid in str(pids).split(";"):
            normalized_pid = _normalize_pid(pid)
            if normalized_pid:
                mapping.setdefault(normalized_pid, set()).add(addr_key)
    return mapping


def _entity_pids(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """{sanitize_owner(reporting_body_name): {pid, ...}}.

    Keyed by sanitize_owner() rather than the verbatim string: raw_lotr_
    ownership is un-deduplicated source data, so the same corporation can
    appear as both "GLR PROPERTIES LTD" and "GLR PROPERTIES LTD." across
    different rows. ownership_claims (via record_claim()'s auto-collapse)
    only ever stores ONE of those spellings, so looking this up by the exact
    string would silently drop whichever variant's PIDs didn't happen to
    match the surviving spelling -- see build_landlord_portfolios(), which
    looks up cluster entities the same normalized way.
    """
    rows = conn.execute(
        "SELECT reporting_body_name, pid FROM raw_lotr_ownership "
        "WHERE reporting_body_name IS NOT NULL AND pid IS NOT NULL"
    ).fetchall()
    pids_by_entity: dict[str, set[str]] = {}
    for reporting_body_name, pid in rows:
        normalized_pid = _normalize_pid(pid)
        if not normalized_pid:
            continue
        pids_by_entity.setdefault(sanitize_owner(reporting_body_name), set()).add(normalized_pid)
    return pids_by_entity


def build_landlord_portfolios(
    conn: sqlite3.Connection, pid_address_map_path: str
) -> dict[str, Portfolio]:
    """Returns {addr_key: Portfolio} for every building reached by a
    confirmed common_owner cluster (resolve_owner_groups()'s default
    confidence gate — same as the rest of the claims model). A cluster
    reaches an addr_key if any entity in it is the reporting body for a PID
    that maps to that addr_key. Buildings outside any cluster, or whose PIDs
    are in neither pid_address_map.csv nor raw_buildings, are simply absent
    from the result.
    """
    point_keys_by_pid = _load_pid_to_addr_keys(pid_address_map_path)
    building_keys_by_pid = _building_pids(conn)
    entity_pids = _entity_pids(conn)
    owner_groups = resolve_owner_groups(conn)

    clusters: list[set[str]] = []
    seen: set[str] = set()
    for entity, others in owner_groups.items():
        if entity in seen:
            continue
        cluster = {entity, *others}
        seen |= cluster
        clusters.append(cluster)

    by_addr_key: dict[str, Portfolio] = {}
    for cluster in clusters:
        pids: set[str] = set()
        for entity in cluster:
            pids |= entity_pids.get(sanitize_owner(entity), set())
        if not pids:
            continue
        building_keys = set().union(*(building_keys_by_pid.get(pid, set()) for pid in pids))
        point_keys = set().union(*(point_keys_by_pid.get(pid, set()) for pid in pids))
        covered_points = set().union(
            *(point_keys_by_pid.get(pid, set()) for pid in pids if pid in building_keys_by_pid)
        )
        addr_keys = building_keys | point_keys
        if not addr_keys:
            continue

        portfolio_name = max(
            sorted(cluster), key=lambda e: len(entity_pids.get(sanitize_owner(e), set()))
        )
        portfolio = Portfolio(
            portfolio_key=sanitize_owner(portfolio_name),
            portfolio_name=portfolio_name,
            entities=sorted(cluster),
            addr_keys=addr_keys,
            building_count=len(building_keys | (point_keys - covered_points)),
        )
        for addr_key in addr_keys:
            by_addr_key[addr_key] = portfolio
    return by_addr_key
