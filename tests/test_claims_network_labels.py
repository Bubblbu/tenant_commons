"""network_label claims: display names for landlord networks (spec
2026-09-23-ownership-layers-design.md §4). The label is free text, never an
entity, so it must not collapse onto entity spellings or appear as one."""

from __future__ import annotations

import logging

import pandas as pd

from tc_core.claims import (
    NETWORK_LABEL,
    confirmed_common_owner_edges,
    find_similar_entity,
    list_known_entities,
    network_label_claims,
    record_claim,
)
from tc_core.db import get_connection, init_db
from tc_core.ingest.ownership_claims import ingest_ownership_claims


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def test_network_label_text_is_stored_verbatim_apart_from_whitespace():
    conn = _conn()
    record_claim(conn, "GLR PROPERTIES LTD.", "  GLR Properties /  Rener family ",
                 NETWORK_LABEL, "manual_research", confidence="confirmed")
    assert conn.execute("SELECT entity_b FROM ownership_claims").fetchone()[0] == (
        "GLR Properties / Rener family"
    )


def test_label_resembling_an_entity_is_not_collapsed_onto_it():
    conn = _conn()
    record_claim(conn, "GLR PROPERTIES LTD.", "RENER, GEORGE", "common_owner",
                 "public_registry", confidence="confirmed")
    record_claim(conn, "RENER, GEORGE", "Glr Properties Ltd", NETWORK_LABEL,
                 "manual_research", confidence="confirmed")
    label = conn.execute(
        "SELECT entity_b FROM ownership_claims WHERE relationship = ?", (NETWORK_LABEL,)
    ).fetchone()[0]
    assert label == "Glr Properties Ltd"


def test_labels_are_not_known_entities():
    conn = _conn()
    record_claim(conn, "GLR PROPERTIES LTD.", "GLR network", NETWORK_LABEL,
                 "manual_research", confidence="confirmed")
    assert list_known_entities(conn) == ["GLR PROPERTIES LTD."]
    assert find_similar_entity(conn, "glr network") is None


def test_network_label_claims_keep_the_latest_confirmed_active_label():
    conn = _conn()
    record_claim(conn, "A LTD", "Old name", NETWORK_LABEL, "manual_research",
                 confidence="confirmed", claim_key="l1")
    record_claim(conn, "A LTD", "New name", NETWORK_LABEL, "manual_research",
                 confidence="confirmed", claim_key="l2")
    record_claim(conn, "B LTD", "Unconfirmed", NETWORK_LABEL, "manual_research", claim_key="l3")
    record_claim(conn, "C LTD", "Retracted", NETWORK_LABEL, "manual_research",
                 confidence="confirmed", status="retracted", claim_key="l4")
    labels = network_label_claims(conn)
    assert {key: value[0] for key, value in labels.items()} == {"a-ltd": "New name"}


def test_confirmed_common_owner_edges_carry_their_source_type():
    conn = _conn()
    record_claim(conn, "A LTD", "B LTD", "common_owner", "public_registry", confidence="confirmed")
    record_claim(conn, "A LTD", "C LTD", "common_owner", "tenant_report", confidence="confirmed")
    record_claim(conn, "A LTD", "D LTD", "common_owner", "manual_research")
    record_claim(conn, "A LTD", "Label", NETWORK_LABEL, "manual_research", confidence="confirmed")
    assert sorted(confirmed_common_owner_edges(conn)) == [
        ("A LTD", "B LTD", "public_registry"),
        ("A LTD", "C LTD", "tenant_report"),
    ]


def test_bulk_import_does_not_report_a_label_as_a_collapsed_entity(tmp_path, caplog):
    conn = _conn()
    record_claim(conn, "GLR PROPERTIES LTD.", "RENER, GEORGE", "common_owner",
                 "public_registry", confidence="confirmed")
    csv = tmp_path / "claims.csv"
    pd.DataFrame([{
        "claim_key": "label-1", "entity_a": "RENER, GEORGE", "entity_b": "Glr Properties Ltd",
        "relationship": NETWORK_LABEL, "source_type": "manual_research", "confidence": "confirmed",
    }]).to_csv(csv, index=False)
    caplog.set_level(logging.INFO, logger="tc_core.ingest")

    ingest_ownership_claims(conn, str(csv))

    assert "Glr Properties Ltd" not in caplog.text
