import sqlite3

from tc_core.db import init_db


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info('{table}')")}


def test_overlay_housing_exists_with_expected_columns():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    cols = _columns(conn, "overlay_housing")
    assert {
        "overlay_id",
        "addr_key",
        "address",
        "housing_name",
        "local_area",
        "lat",
        "lon",
        "is_coop",
        "is_sro",
        "coop_status",
        "sro_owner",
        "source_row_ids",
        "ingested_at",
    } <= cols


def test_overlay_housing_is_rebuildable():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO overlay_housing (addr_key, address, lat, lon, ingested_at) "
        "VALUES ('x', 'x', 1.0, 2.0, 'now')"
    )
    conn.commit()
    init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM overlay_housing").fetchone()[0] == 0


def test_ownership_claims_still_survives_rebuild():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO ownership_claims (claim_key, entity_a, entity_b, relationship, "
        "source_type, created_at, updated_at) "
        "VALUES ('k', 'a', 'b', 'same_entity', 'manual_research', 'now', 'now')"
    )
    conn.commit()
    init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM ownership_claims").fetchone()[0] == 1
