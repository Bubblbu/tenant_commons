"""Per-building registered owners from the BC Land Owner Transparency Registry.

A building's registered owners are the LOTR reporting bodies filed against
its PIDs (bridged to addr_key by pid_address_map.csv). The primary owner holds
the most of the building's PIDs, ties broken alphabetically. Spelling variants
of one body ("GLR PROPERTIES LTD" / "GLR PROPERTIES LTD.") count as one owner,
shown by its most frequent spelling.
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..normalize import sanitize_owner
from .portfolios import _load_pid_to_addr_key, _normalize_pid


@dataclass
class RegistryOwnership:
    owners: list[str]
    pids: list[str]
    # Date the registry record was retrieved (Samwise order date), not a filing date.
    retrieved: str | None


def build_registry_owners(
    conn: sqlite3.Connection, pid_address_map_path: str
) -> dict[str, RegistryOwnership]:
    pid_to_addr_key = _load_pid_to_addr_key(pid_address_map_path)
    rows = conn.execute(
        "SELECT pid, reporting_body_name, order_created_date FROM raw_lotr_ownership "
        "WHERE reporting_body_name IS NOT NULL AND pid IS NOT NULL "
        "AND (data_fetch_status IS NULL OR data_fetch_status = 'SUCCESS')"
    ).fetchall()

    body_pids: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    spellings: dict[str, Counter] = defaultdict(Counter)
    filed: dict[str, set[str]] = defaultdict(set)
    retrieved: dict[str, str] = {}
    for pid, name, created in rows:
        addr_key = pid_to_addr_key.get(_normalize_pid(pid))
        if addr_key is None:
            continue
        name = name.strip()
        body = sanitize_owner(name)
        body_pids[addr_key][body].add(_normalize_pid(pid))
        spellings[body][name] += 1
        filed[addr_key].add(pid.strip())
        if created:
            day = str(created).split(" ")[0].split("T")[0]
            if day > retrieved.get(addr_key, ""):
                retrieved[addr_key] = day

    def display(body: str) -> str:
        counts = spellings[body]
        top = max(counts.values())
        return min(name for name, count in counts.items() if count == top)

    result: dict[str, RegistryOwnership] = {}
    for addr_key, bodies in body_pids.items():
        ranked = sorted(bodies, key=lambda body: (-len(bodies[body]), display(body)))
        result[addr_key] = RegistryOwnership(
            owners=[display(body) for body in ranked],
            pids=sorted(filed[addr_key]),
            retrieved=retrieved.get(addr_key),
        )
    return result
