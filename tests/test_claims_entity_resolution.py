"""Targeted tests for the claims-merge entity-resolution logic (CLAUDE.md
Section 6: "claims-merge logic" needs real tests, not eyeballing, because a
silent regression here corrupts the project's core IP asset).

Covers the specific gap that motivated this: "GLR PROPERTIES LTD" and "GLR
PROPERTIES LTD." (trailing period) previously accumulated as two distinct
stored entities instead of one, silently splitting a landlord's portfolio.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sica_core.claims import record_claim
from sica_core.db import get_connection, init_db
from sica_core.ingest.lotr_claims import _build_groups


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def test_record_claim_collapses_trailing_punctuation_variant():
    conn = _conn()
    record_claim(
        conn,
        entity_a="GLR PROPERTIES LTD",
        entity_b="RENER, LUDVIK",
        relationship="common_owner",
        source_type="public_registry",
        confidence="confirmed",
    )
    record_claim(
        conn,
        entity_a="GLR PROPERTIES LTD.",
        entity_b="RENER, GEORGE",
        relationship="common_owner",
        source_type="public_registry",
        confidence="confirmed",
    )

    rows = conn.execute("SELECT DISTINCT entity_a FROM ownership_claims").fetchall()
    assert [r[0] for r in rows] == ["GLR PROPERTIES LTD"]


def test_record_claim_leaves_genuinely_different_entities_alone():
    conn = _conn()
    record_claim(
        conn,
        entity_a="IOCO PC LAND HOLDINGS LTD",
        entity_b="SOME HOLDER",
        relationship="common_owner",
        source_type="public_registry",
        confidence="confirmed",
    )
    record_claim(
        conn,
        entity_a="IOCO PM LAND HOLDINGS LTD",
        entity_b="ANOTHER HOLDER",
        relationship="common_owner",
        source_type="public_registry",
        confidence="confirmed",
    )

    rows = conn.execute(
        "SELECT DISTINCT entity_a FROM ownership_claims ORDER BY 1"
    ).fetchall()
    assert [r[0] for r in rows] == ["IOCO PC LAND HOLDINGS LTD", "IOCO PM LAND HOLDINGS LTD"]


def test_lotr_build_groups_collapses_punctuation_variant_within_one_import():
    rows = [
        ("007265280", "GLR PROPERTIES LTD", "RENER, LUDVIK", "Registered owner", "2024-01-01"),
        ("007265281", "GLR PROPERTIES LTD.", "RENER, LUDVIK", "Registered owner", "2024-02-01"),
    ]
    groups = _build_groups(rows)
    assert len(groups) == 1
    (group,) = groups.values()
    assert group.pids == {"007265280", "007265281"}
