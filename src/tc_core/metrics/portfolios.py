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
pid_address_map.csv bridges PID -> addr_key. So a resolve_owner_groups()
cluster's full building footprint can be computed independent of any older
business-name label.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from ..claims import confirmed_common_owner_edges, network_label_claims, resolve_owner_groups
from ..normalize import sanitize_owner

REGISTRY_SOURCE = "public_registry"


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
    # Stable id: sanitize_owner() of the default name, whatever the display
    # name — relabelling a network through a claim never changes its key.
    portfolio_key: str
    # Display name: a confirmed network_label claim if any entity in the
    # cluster has one (latest wins), else the entity holding the most PIDs
    # (ties alphabetical).
    portfolio_name: str
    name_source: str  # "default" | "claim"
    entities: list[str]
    addr_keys: set[str] = field(default_factory=set)
    # Confirmed common_owner claims inside the cluster, by public source
    # category: "registry" (public_registry) or "vtu_research" (all others).
    evidence: dict[str, int] = field(default_factory=dict)


def _load_pid_to_addr_key(path: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid = _normalize_pid(row.get("pid") or "")
            addr_key = (row.get("addr_key") or "").strip()
            if pid and addr_key:
                mapping[pid] = addr_key
    return mapping


def _entity_pids(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """{sanitize_owner(reporting_body_name): {pid, ...}}.

    Keyed by sanitize_owner() rather than the verbatim string: raw_lotr_
    ownership is un-deduplicated source data, so the same corporation can
    appear as both "GLR PROPERTIES LTD" and "GLR PROPERTIES LTD." across rows,
    while ownership_claims stores only one of those spellings.
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


def _clusters(conn: sqlite3.Connection) -> list[list[str]]:
    clusters: list[list[str]] = []
    seen: set[str] = set()
    for entity, others in resolve_owner_groups(conn).items():
        if entity in seen:
            continue
        cluster = {entity, *others}
        seen |= cluster
        clusters.append(sorted(cluster))
    return clusters


def build_landlord_portfolios(
    conn: sqlite3.Connection, pid_address_map_path: str
) -> dict[str, Portfolio]:
    """Returns {addr_key: Portfolio} for every building reached by a confirmed
    common_owner cluster. A cluster reaches an addr_key if any of its entities
    is the reporting body for a PID mapped to it. A building reached by
    several clusters goes to the one holding most of its PIDs, then the
    larger cluster (more addr_keys), then the smaller key — independent of
    claim order.
    """
    pid_to_addr_key = _load_pid_to_addr_key(pid_address_map_path)
    entity_pids = _entity_pids(conn)
    labels = network_label_claims(conn)
    clusters = _clusters(conn)

    cluster_of = {entity: i for i, cluster in enumerate(clusters) for entity in cluster}
    evidence = [{"registry": 0, "vtu_research": 0} for _ in clusters]
    for a, b, source_type in confirmed_common_owner_edges(conn):
        i = cluster_of.get(a)
        if i is not None and cluster_of.get(b) == i:
            evidence[i]["registry" if source_type == REGISTRY_SOURCE else "vtu_research"] += 1

    portfolios: list[Portfolio] = []
    portfolio_pids: list[set[str]] = []
    for i, cluster in enumerate(clusters):
        pids: set[str] = set()
        for entity in cluster:
            pids |= entity_pids.get(sanitize_owner(entity), set())
        addr_keys = {pid_to_addr_key[pid] for pid in pids if pid in pid_to_addr_key}
        if not addr_keys:
            continue
        default_name = max(cluster, key=lambda e: len(entity_pids.get(sanitize_owner(e), set())))
        label = max(
            (labels[key] for key in {sanitize_owner(e) for e in cluster} if key in labels),
            key=lambda claim: (claim[1], claim[2]),
            default=None,
        )
        portfolios.append(
            Portfolio(
                portfolio_key=sanitize_owner(default_name),
                portfolio_name=label[0] if label else default_name,
                name_source="claim" if label else "default",
                entities=cluster,
                addr_keys=addr_keys,
                evidence=evidence[i],
            )
        )
        portfolio_pids.append(pids)

    pid_counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for j, pids in enumerate(portfolio_pids):
        for pid in pids:
            addr_key = pid_to_addr_key.get(pid)
            if addr_key is not None:
                pid_counts[addr_key][j] += 1

    by_addr_key: dict[str, Portfolio] = {}
    for addr_key, per_portfolio in pid_counts.items():
        best = min(
            per_portfolio,
            key=lambda j: (-per_portfolio[j], -len(portfolios[j].addr_keys), portfolios[j].portfolio_key),
        )
        by_addr_key[addr_key] = portfolios[best]
    return by_addr_key
