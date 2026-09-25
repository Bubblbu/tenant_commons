"""Per-building registered owners from the BC Land Owner Transparency Registry.

A building's registered owners are the LOTR reporting bodies filed against
its PIDs (bridged to addr_key by pid_address_map.csv and the PIDs on the
building records, as for landlord networks). The primary owner holds
the most of the building's PIDs, ties broken alphabetically. Spelling variants
of one body ("GLR PROPERTIES LTD" / "GLR PROPERTIES LTD.") count as one owner,
shown by its most frequent spelling.
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..normalize import sanitize_owner
from .portfolios import _normalize_pid, pid_addr_keys


@dataclass
class RegistryOwnership:
    owners: list[str]
    pids: list[str]
    # Date the registry record was retrieved (Samwise order date), not a filing date.
    retrieved: str | None


def build_registry_owners(
    conn: sqlite3.Connection, pid_address_map_path: str
) -> dict[str, RegistryOwnership]:
    keys_by_pid = pid_addr_keys(conn, pid_address_map_path)
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
        addr_keys = keys_by_pid.get(_normalize_pid(pid))
        if not addr_keys:
            continue
        name = name.strip()
        body = sanitize_owner(name)
        spellings[body][name] += 1
        day = str(created).split(" ")[0].split("T")[0] if created else ""
        for addr_key in addr_keys:
            body_pids[addr_key][body].add(_normalize_pid(pid))
            filed[addr_key].add(pid.strip())
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
