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
from dataclasses import dataclass, field

from ..normalize import sanitize_owner
from .portfolios import _normalize_pid, pid_addr_keys


@dataclass
class RegistryOwnership:
    owners: list[str]
    pids: list[str]
    # Date the registry record was retrieved (Samwise order date), not a filing date.
    retrieved: str | None
    # Each owner's own PIDs (as filed), so joint owners of one parcel can be
    # told apart from owners of separate parcels.
    owner_pids: dict[str, list[str]] = field(default_factory=dict)


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
    filed_spelling: dict[str, str] = {}
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
            filed_spelling[_normalize_pid(pid)] = pid.strip()
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
            owner_pids={
                display(body): sorted(filed_spelling[p] for p in bodies[body]) for body in ranked
            },
        )
    return result


def build_registry_searches(
    conn: sqlite3.Connection, pid_address_map_path: str
) -> dict[str, str]:
    """{addr_key: date} for buildings with a PID searched on LOTR without a filing.

    A PID counts when its latest search (raw_lotr_searches) found no filing and
    raw_lotr_ownership holds no filing for it either; the date is the latest
    such search across the building's PIDs. Callers show it only where the
    building has no registry owner. Notes stay internal.
    """
    keys_by_pid = pid_addr_keys(conn, pid_address_map_path)
    filed = {
        _normalize_pid(pid) for (pid,) in conn.execute(
            "SELECT pid FROM raw_lotr_ownership WHERE pid IS NOT NULL "
            "AND (data_fetch_status IS NULL OR data_fetch_status = 'SUCCESS')"
        )
    }
    latest: dict[str, tuple[str, str, str]] = {}
    for pid, searched_on, searched_at, result in conn.execute(
        "SELECT pid, searched_on, searched_at, result FROM raw_lotr_searches"
    ):
        pid = _normalize_pid(pid)
        when = (searched_on, searched_at or "")
        if pid not in latest or when > latest[pid][:2]:
            latest[pid] = (*when, result)

    result: dict[str, str] = {}
    for pid, (searched_on, _, outcome) in latest.items():
        if outcome != "no_filing" or pid in filed:
            continue
        for addr_key in keys_by_pid.get(pid, ()):
            if searched_on > result.get(addr_key, ""):
                result[addr_key] = searched_on
    return result


# type_of_interest prefixes -> the public interest label. RB_CORPORATION (and a
# trustee row naming the reporting body itself) is the owner, not someone behind it.
_INTERESTS = (
    ("INTEREST_HOLDER", "interest holder"),
    ("RB_TRUSTEE_", "trustee"),
    ("RB_TRUST_SETTLOR_", "settlor"),
    ("RB_PARTNER_", "partner"),
)


def _interest(type_of_interest: str | None) -> str | None:
    for prefix, label in _INTERESTS:
        if type_of_interest and type_of_interest.startswith(prefix):
            return label
    return None


def build_interest_holders(
    conn: sqlite3.Connection, pid_address_map_path: str
) -> dict[str, list[dict]]:
    """{addr_key: [{name, interest, pids}]} — who stands behind the reporting
    bodies on a building's PIDs. Public: name and interest type only. The
    query reads no residence, citizenship or address column, so none can
    reach an artifact from here."""
    keys_by_pid = pid_addr_keys(conn, pid_address_map_path)
    rows = conn.execute(
        "SELECT pid, reporting_body_name, type_of_interest, holder_name FROM raw_lotr_ownership "
        "WHERE holder_name IS NOT NULL AND TRIM(holder_name) != '' AND pid IS NOT NULL "
        "AND (data_fetch_status IS NULL OR data_fetch_status = 'SUCCESS') "
        # Identities withheld under LOTR s. 30(4) stay withheld, whatever the name field holds.
        "AND COALESCE(LOWER(individual_is_full_name_omitted), '0') NOT IN ('1', 'true') "
        "AND COALESCE(TRIM(obscure_message), '') = ''"
    ).fetchall()
    found: dict[str, dict[tuple[str, str], set[str]]] = defaultdict(lambda: defaultdict(set))
    spellings: dict[str, Counter] = defaultdict(Counter)
    for pid, body, type_of_interest, holder in rows:
        interest = _interest(type_of_interest)
        holder = holder.strip()
        if interest is None or sanitize_owner(holder) == sanitize_owner(body):
            continue
        key = sanitize_owner(holder)
        spellings[key][holder] += 1
        for addr_key in keys_by_pid.get(_normalize_pid(pid), ()):
            found[addr_key][(key, interest)].add(pid.strip())

    def display(key: str) -> str:
        counts = spellings[key]
        top = max(counts.values())
        return min(name for name, n in counts.items() if n == top)

    return {
        addr_key: [
            {"name": display(key), "interest": interest, "pids": sorted(pids)}
            for (key, interest), pids in sorted(
                holders.items(), key=lambda kv: (-len(kv[1]), display(kv[0][0]))
            )
        ]
        for addr_key, holders in found.items()
    }
