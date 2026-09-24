"""Shared write path for ownership_claims — the manually-curated ownership
research layer described in CLAUDE.md Section 3 ("Claims model").

`record_claim()` is the one place a claim actually gets written, called by
both the bulk-CSV importer (`ingest/ownership_claims.py`) and, later, a
single-record entry form — so there's one implementation of the upsert-by-
claim_key logic and the write-time entity normalization, not two.

Entity resolution: this project deliberately has no canonical-entities/alias
table. Trivial spelling/formatting noise (case, stray whitespace, list-like
string artifacts, punctuation like a trailing period on a legal suffix) is
collapsed automatically here — clean_owner_label() handles display cleanup,
and record_claim() additionally collapses onto an existing entity's exact
stored spelling whenever only that kind of noise differs (via
find_similar_entity()'s sanitize_owner()-based key), so "GLR PROPERTIES LTD"
and "GLR PROPERTIES LTD." always accumulate under one stored entity_a/
entity_b string instead of silently splitting a portfolio in two. Everything
else — a numbered company turning out to be a named person, two
differently-spelled names turning out to be the same legal entity, two
legally-distinct entities sharing a beneficial owner — is recorded as a
claim, not merged at the schema level. Relationship-value convention:
`same_entity` means "this is literally the same legal entity, just written
differently"; `common_owner` means "different entities, same real owner".
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from .normalize import clean_owner_label, sanitize_owner

_CLAIM_FIELDS = (
    "entity_a",
    "entity_b",
    "relationship",
    "source_type",
    "source_note",
    "reported_by",
    "date_reported",
    "confidence",
    "status",
    "retracted_at",
    "retracted_reason",
)

# Names a landlord network: entity_a is any entity in a common_owner cluster,
# entity_b is display text (never an entity — see record_claim()).
NETWORK_LABEL = "network_label"


def _resolve_entity_label(conn: sqlite3.Connection, entity: str) -> str:
    """clean_owner_label() plus an automatic collapse onto an existing
    entity's exact stored spelling when only trivial formatting noise
    (case/whitespace/punctuation) differs, via find_similar_entity()'s
    sanitize_owner()-based key. Genuine entity resolution — a numbered
    company turning out to be a named person — is deliberately NOT handled
    here; see module docstring.
    """
    cleaned = clean_owner_label(entity)
    return find_similar_entity(conn, cleaned) or cleaned


def record_claim(
    conn: sqlite3.Connection,
    entity_a: str,
    entity_b: str,
    relationship: str,
    source_type: str,
    *,
    source_note: str | None = None,
    reported_by: str | None = None,
    date_reported: str | None = None,
    confidence: str = "unconfirmed",
    status: str = "active",
    retracted_at: str | None = None,
    retracted_reason: str | None = None,
    claim_key: str | None = None,
) -> int:
    """Insert or update (by claim_key) one ownership_claims row.

    Existing claim_key -> UPDATE in place (bumps updated_at, leaves
    created_at and claim_id untouched). New/omitted claim_key -> INSERT
    (auto-generating a UUID if the caller didn't supply one). Returns the
    row's claim_id either way.

    entity_a/entity_b are passed through clean_owner_label() before storage,
    then collapsed onto an existing entity's exact stored spelling if one
    with the same sanitize_owner() key already exists — collapses case/
    whitespace/punctuation/list-artifact noise so trivial spelling variants
    never accumulate as separate stored entities; see module docstring for
    why genuine entity resolution deliberately isn't handled here.
    """
    for field_name, value in (
        ("entity_a", entity_a),
        ("entity_b", entity_b),
        ("relationship", relationship),
        ("source_type", source_type),
    ):
        if value is None or not str(value).strip():
            raise ValueError(f"record_claim: {field_name} is required and cannot be empty")

    entity_a = _resolve_entity_label(conn, entity_a)
    if relationship == NETWORK_LABEL:
        entity_b = " ".join(str(entity_b).split())
    else:
        entity_b = _resolve_entity_label(conn, entity_b)
    claim_key = claim_key or uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()

    with conn:
        existing = conn.execute(
            "SELECT claim_id FROM ownership_claims WHERE claim_key = ?", (claim_key,)
        ).fetchone()
        if existing is None:
            cur = conn.execute(
                """
                INSERT INTO ownership_claims (
                    claim_key, entity_a, entity_b, relationship, source_type,
                    source_note, reported_by, date_reported, confidence, status,
                    retracted_at, retracted_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_key, entity_a, entity_b, relationship, source_type,
                    source_note, reported_by, date_reported, confidence, status,
                    retracted_at, retracted_reason, now, now,
                ),
            )
            return cur.lastrowid
        claim_id = existing[0]
        conn.execute(
            """
            UPDATE ownership_claims SET
                entity_a = ?, entity_b = ?, relationship = ?, source_type = ?,
                source_note = ?, reported_by = ?, date_reported = ?,
                confidence = ?, status = ?, retracted_at = ?, retracted_reason = ?,
                updated_at = ?
            WHERE claim_id = ?
            """,
            (
                entity_a, entity_b, relationship, source_type,
                source_note, reported_by, date_reported,
                confidence, status, retracted_at, retracted_reason,
                now, claim_id,
            ),
        )
        return claim_id


def list_known_entities(conn: sqlite3.Connection) -> list[str]:
    """Distinct entity_a/entity_b values currently in ownership_claims.

    For future form autocomplete, and as the basis for the soft
    duplicate-warning check in ingest/ownership_claims.py.
    """
    rows = conn.execute(
        "SELECT entity_a AS entity FROM ownership_claims "
        "UNION SELECT entity_b FROM ownership_claims WHERE relationship != ? "
        "ORDER BY 1",
        (NETWORK_LABEL,),
    ).fetchall()
    return [r[0] for r in rows]


def find_similar_entity(conn: sqlite3.Connection, entity: str) -> str | None:
    """Return an existing known entity whose sanitize_owner() key matches
    `entity`'s, if the exact display text differs — a soft nudge that two
    names might be the same entity typed differently, not a hard merge.
    Returns None if there's no such match (including an exact-text match,
    which isn't a variant worth flagging).
    """
    target_key = sanitize_owner(entity)
    target_label = clean_owner_label(entity)
    for known in list_known_entities(conn):
        if known == target_label:
            continue
        if sanitize_owner(known) == target_key:
            return known
    return None


def _cluster_by_relationship(
    conn: sqlite3.Connection,
    relationship: str,
    *,
    include_unconfirmed: bool = False,
) -> list[set[str]]:
    """Connected components over active claims of the given relationship.
    Confirmed-only by default — see record_claim()'s module docstring on why
    an unconfirmed same_entity/common_owner claim shouldn't drive a merged
    or grouped display on its own. Returned sets are of entity display
    strings exactly as stored (already clean_owner_label()-normalized).
    """
    confidences = ("confirmed",) if not include_unconfirmed else ("confirmed", "unconfirmed")
    placeholders = ",".join("?" * len(confidences))
    rows = conn.execute(
        f"""
        SELECT entity_a, entity_b FROM ownership_claims
        WHERE relationship = ? AND status = 'active' AND confidence IN ({placeholders})
        """,
        (relationship, *confidences),
    ).fetchall()

    adjacency: dict[str, set[str]] = {}
    for entity_a, entity_b in rows:
        adjacency.setdefault(entity_a, set()).add(entity_b)
        adjacency.setdefault(entity_b, set()).add(entity_a)

    seen: set[str] = set()
    clusters: list[set[str]] = []
    for node in adjacency:
        if node in seen:
            continue
        stack = [node]
        cluster: set[str] = set()
        while stack:
            current = stack.pop()
            if current in cluster:
                continue
            cluster.add(current)
            stack.extend(adjacency.get(current, ()) - cluster)
        seen |= cluster
        clusters.append(cluster)
    return clusters


def resolve_entity_clusters(
    conn: sqlite3.Connection, *, include_unconfirmed: bool = False
) -> dict[str, str]:
    """same_entity clusters -> one joined display name shared by every
    entity in the cluster, e.g. {'0733603 BC Ltd': '0733603 BC Ltd / Phil
    Kim', 'Phil Kim': '0733603 BC Ltd / Phil Kim'}. Deliberately no "primary"
    name is chosen — every known name for the entity is shown, not one
    picked over the others (see the design discussion this came from).
    Entities not part of any same_entity cluster are simply absent from the
    returned dict; callers fall back to the raw name themselves via
    display_name_for().
    """
    result: dict[str, str] = {}
    for cluster in _cluster_by_relationship(
        conn, "same_entity", include_unconfirmed=include_unconfirmed
    ):
        joined = " / ".join(sorted(cluster))
        for entity in cluster:
            result[entity] = joined
    return result


def display_name_for(entity: str, clusters: dict[str, str]) -> str:
    """Look up entity in a resolve_entity_clusters() result, falling back
    to the entity's own name if it isn't part of any same_entity cluster.
    """
    return clusters.get(entity, entity)


def resolve_owner_groups(
    conn: sqlite3.Connection, *, include_unconfirmed: bool = False
) -> dict[str, list[str]]:
    """common_owner clusters -> the OTHER entities sharing common ownership
    with a given one (sorted, excluding the entity itself). Unlike
    resolve_entity_clusters(), these are legally distinct entities that
    happen to share a real owner — deliberately NOT collapsed into one
    display name; callers should present them as a group/portfolio (e.g.
    CLAUDE.md's planned "claims-derived landlord clustering" on the map),
    with each entity keeping its own name. Entities not part of any
    common_owner cluster are simply absent from the returned dict.
    """
    result: dict[str, list[str]] = {}
    for cluster in _cluster_by_relationship(
        conn, "common_owner", include_unconfirmed=include_unconfirmed
    ):
        for entity in cluster:
            result[entity] = sorted(cluster - {entity})
    return result


def network_label_claims(conn: sqlite3.Connection) -> dict[str, tuple[str, str, int]]:
    """sanitize_owner(entity) -> (label, updated_at, claim_id) of the latest
    confirmed, active network_label claim naming that entity."""
    rows = conn.execute(
        "SELECT entity_a, entity_b, updated_at, claim_id FROM ownership_claims "
        "WHERE relationship = ? AND status = 'active' AND confidence = 'confirmed' "
        "ORDER BY updated_at, claim_id",
        (NETWORK_LABEL,),
    ).fetchall()
    return {
        sanitize_owner(entity): (label, updated_at, claim_id)
        for entity, label, updated_at, claim_id in rows
    }


def confirmed_common_owner_edges(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """(entity_a, entity_b, source_type) of every confirmed, active common_owner claim."""
    rows = conn.execute(
        "SELECT entity_a, entity_b, source_type FROM ownership_claims "
        "WHERE relationship = 'common_owner' AND status = 'active' AND confidence = 'confirmed'"
    ).fetchall()
    return [(a, b, source_type) for a, b, source_type in rows]
