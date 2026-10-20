"""entity_kind / institutional claims: a claim about one entity, with the
value in entity_b (the network_label precedent, spec 2026-10-20)."""

from __future__ import annotations

import pytest

from tc_core.claims import (
    ENTITY_KIND,
    INSTITUTIONAL,
    entity_attribute_claims,
    find_similar_entity,
    list_known_entities,
    record_claim,
)
from tc_core.db import get_connection, init_db
from tc_core.normalize import sanitize_owner


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def test_attribute_value_is_stored_lowercase_and_validated():
    conn = _conn()
    record_claim(conn, "Sun Life Assurance Company of Canada", " Insurer ", INSTITUTIONAL,
                 "manual_research", confidence="confirmed")
    assert conn.execute("SELECT entity_b FROM ownership_claims").fetchone()[0] == "insurer"


def test_attribute_value_outside_vocabulary_is_rejected():
    conn = _conn()
    with pytest.raises(ValueError, match="entity_kind"):
        record_claim(conn, "0733603 BC Ltd", "numbered company", ENTITY_KIND, "manual_research")


def test_unknown_is_not_a_claimable_kind():
    conn = _conn()
    with pytest.raises(ValueError, match="entity_kind"):
        record_claim(conn, "Acme Ltd", "unknown", ENTITY_KIND, "manual_research")


def test_attribute_values_are_not_entities():
    conn = _conn()
    record_claim(conn, "Mennonite Senior Citizens Society of BC", "non_profit", ENTITY_KIND,
                 "manual_research", confidence="confirmed")
    assert list_known_entities(conn) == ["Mennonite Senior Citizens Society of BC"]
    assert find_similar_entity(conn, "NON PROFIT") is None


def test_latest_confirmed_claim_wins_and_unconfirmed_is_ignored():
    conn = _conn()
    record_claim(conn, "Acme Ltd", "company", ENTITY_KIND, "manual_research",
                 confidence="confirmed", claim_key="a")
    record_claim(conn, "Acme Ltd", "trust", ENTITY_KIND, "tenant_report",
                 confidence="confirmed", claim_key="b")
    record_claim(conn, "Acme Ltd", "partnership", ENTITY_KIND, "manual_research", claim_key="c")
    assert entity_attribute_claims(conn, ENTITY_KIND) == {sanitize_owner("Acme Ltd"): ("trust", "tenant_report")}
    assert entity_attribute_claims(conn, ENTITY_KIND, include_unconfirmed=True)[sanitize_owner("Acme Ltd")][0] == "partnership"


def test_retracted_attribute_claim_stops_applying():
    conn = _conn()
    record_claim(conn, "Acme Ltd", "trust", ENTITY_KIND, "manual_research",
                 confidence="confirmed", claim_key="a")
    record_claim(conn, "Acme Ltd", "trust", ENTITY_KIND, "manual_research",
                 confidence="confirmed", status="retracted", claim_key="a")
    assert entity_attribute_claims(conn, ENTITY_KIND) == {}


def test_bulk_import_does_not_report_an_attribute_value_as_a_collapsed_entity(tmp_path, caplog):
    import logging

    from tc_core.ingest.ownership_claims import ingest_ownership_claims

    conn = _conn()
    record_claim(conn, "Trust", "RENER, GEORGE", "common_owner", "public_registry", confidence="confirmed")
    csv = tmp_path / "claims.csv"
    csv.write_text(
        "claim_key,entity_a,entity_b,relationship,source_type,confidence\n"
        f"kind-1,Kerrisdale Family Trust,trust,{ENTITY_KIND},manual_research,confirmed\n"
    )
    caplog.set_level(logging.INFO, logger="tc_core.ingest")

    ingest_ownership_claims(conn, str(csv))

    assert "'trust' auto-collapsed" not in caplog.text
    assert entity_attribute_claims(conn, ENTITY_KIND)[sanitize_owner("Kerrisdale Family Trust")][0] == "trust"
