"""Derive ownership_claims from raw_lotr_ownership.

The BC Land Owner Transparency Registry (via Samwise) discloses, per
property, which corporation reports an interest and who actually holds that
interest (an individual, or another corporation/trust acting as trustee or
settlor). Two corporations that disclose the same real holder are, in
CLAUDE.md's terms, "secretly the same landlord" — exactly the pattern
ownership_claims exists to record.

Every qualifying (reporting_body, holder) pair becomes one common_owner
claim, deduplicated across however many properties/filings connect that
same pair. Using the holder as a graph node (rather than emitting pairwise
claims directly between reporting bodies) is deliberate: claims.py's
resolve_owner_groups() clusters entities by connected components over
common_owner edges, so a holder disclosed against N different corporations
automatically clusters all N into one portfolio without this module needing
to compute that itself.

Two kinds of rows are dropped before grouping:
- Self-referential rows, where holder_name is just the reporting corp's own
  name (LOTR requires a corp to disclose itself as the "direct" holder of
  its own interest in many cases) — no second entity, nothing to link.
- Rows with no disclosed holder identity at all (redacted under s. 30(4) of
  the Act, or otherwise blank) — no entity_b to record.

confidence='confirmed': treated as sufficient on its own, since this is a
legally-mandated registry disclosure rather than unverified tenant
testimony — see the source_type='public_registry' convention in CLAUDE.md
Section 3. This also means these claims participate in the default
(confirmed-only) common_owner clustering immediately.
"""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

from ..claims import record_claim
from ..normalize import sanitize_owner


class _Group(NamedTuple):
    entity_a: str
    entity_b: str
    pids: set[str]
    interests: set[str]
    dates: list[str]


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _build_groups(rows: list[tuple]) -> dict[tuple[str, str], _Group]:
    # Grouping key is sanitize_owner() (case/punctuation/whitespace-insensitive),
    # not a plain casefold+strip -- otherwise "GLR PROPERTIES LTD" and "GLR
    # PROPERTIES LTD." (trailing period) become two separate groups here, one
    # of the ways a real landlord's portfolio can silently get split in two.
    groups: dict[tuple[str, str], _Group] = {}
    for pid, reporting_body_name, holder_name, type_of_interest, order_created_date in rows:
        entity_a = _clean(reporting_body_name)
        entity_b = _clean(holder_name)
        if entity_a is None or entity_b is None:
            continue
        if sanitize_owner(entity_a) == sanitize_owner(entity_b):
            continue

        key = (sanitize_owner(entity_a), sanitize_owner(entity_b))
        group = groups.get(key)
        if group is None:
            group = _Group(entity_a=entity_a, entity_b=entity_b, pids=set(), interests=set(), dates=[])
            groups[key] = group
        if pid:
            group.pids.add(pid)
        if type_of_interest:
            group.interests.add(type_of_interest)
        if order_created_date:
            group.dates.append(str(order_created_date))
    return groups


def _source_note(group: _Group) -> str:
    n = len(group.pids)
    unit = "property" if n == 1 else "properties"
    interests = ", ".join(sorted(group.interests)) or "unspecified interest"
    example_pids = ", ".join(sorted(group.pids)[:3])
    return (
        f"BC Land Owner Transparency Registry: {group.entity_b} disclosed as holder "
        f"({interests}) of {group.entity_a}'s interest on {n} {unit} "
        f"(e.g. PID {example_pids}). Imported from Samwise export via raw_lotr_ownership."
    )


def derive_lotr_ownership_claims(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT pid, reporting_body_name, holder_name, type_of_interest, order_created_date
        FROM raw_lotr_ownership
        WHERE data_fetch_status IS NULL OR data_fetch_status = 'SUCCESS'
        """
    ).fetchall()

    groups = _build_groups(rows)

    count = 0
    for group in groups.values():
        date_reported = max(group.dates).split(" ")[0] if group.dates else None
        claim_key = f"lotr-{sanitize_owner(group.entity_a)}--{sanitize_owner(group.entity_b)}"
        record_claim(
            conn,
            entity_a=group.entity_a,
            entity_b=group.entity_b,
            relationship="common_owner",
            source_type="public_registry",
            source_note=_source_note(group),
            date_reported=date_reported,
            confidence="confirmed",
            status="active",
            claim_key=claim_key,
        )
        count += 1
    return count
