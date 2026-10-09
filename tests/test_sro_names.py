"""Curated corrections to the City's SRO inventory names (src/tc_core/sro_names.txt)."""

from tc_core.sro_names import SroName, load_sro_names, parse_sro_names, sro_name_claims

SAMPLE = """\
# comment lines and blank lines are ignored

Atira Women's Resourc => Atira Women's Resource Society
Chris Wall - 1030163 BC Ltd => 1030163 BC Ltd | behind: Chris Wall
Giovanni & Catherine Casu - Casu Holdings Ltd => Casu Holdings Ltd | behind: Giovanni Casu; Catherine Casu
Bob Leung and Richard Chang => owners: Bob Leung; Richard Chang
Ging, Huie S (15 year lease to Chris Wall) => Ging, Huie S | manager: Chris Wall
Andrew Charney
"""


def test_parses_every_kind_of_line():
    names = parse_sro_names(SAMPLE)
    assert names["Atira Women's Resourc"] == SroName(owners=["Atira Women's Resource Society"])
    assert names["Chris Wall - 1030163 BC Ltd"] == SroName(owners=["1030163 BC Ltd"], behind=["Chris Wall"])
    assert names["Giovanni & Catherine Casu - Casu Holdings Ltd"].behind == ["Giovanni Casu", "Catherine Casu"]
    assert names["Bob Leung and Richard Chang"] == SroName(owners=["Bob Leung", "Richard Chang"])
    assert names["Ging, Huie S (15 year lease to Chris Wall)"] == SroName(owners=["Ging, Huie S"], manager="Chris Wall")
    assert "Andrew Charney" not in names  # unchanged lines are not corrections


def test_behind_lines_become_city_record_claims():
    claims = sro_name_claims(parse_sro_names(SAMPLE))
    assert ("1030163 BC Ltd", "Chris Wall") in [(c["entity_a"], c["entity_b"]) for c in claims]
    assert {c["relationship"] for c in claims} == {"common_owner"}
    assert {c["source_type"] for c in claims} == {"city_record"}
    keys = [c["claim_key"] for c in claims]
    assert len(keys) == len(set(keys)) == 3  # Chris Wall + the two Casus
    assert keys == [c["claim_key"] for c in sro_name_claims(parse_sro_names(SAMPLE))]  # stable


def test_committed_file_parses_and_carries_no_unchanged_lines():
    names = load_sro_names()
    assert names["Bob Leung and Richard Chang"].owners == ["Bob Leung", "Richard Chang"]
    assert all(n.owners for n in names.values())


def test_import_records_claims_once(tmp_path):
    import sqlite3

    from tc_core.db import init_db
    from tc_core.ingest.sro_claims import import_sro_name_claims

    conn = sqlite3.connect(":memory:")
    init_db(conn)
    names = parse_sro_names(SAMPLE)
    assert import_sro_name_claims(conn, names) == 3
    assert import_sro_name_claims(conn, names) == 3  # upsert, not a second copy
    rows = conn.execute(
        "SELECT entity_a, entity_b, source_type, confidence, status FROM ownership_claims ORDER BY 1, 2"
    ).fetchall()
    assert rows == [
        ("1030163 BC Ltd", "Chris Wall", "city_record", "confirmed", "active"),
        ("Casu Holdings Ltd", "Catherine Casu", "city_record", "confirmed", "active"),
        ("Casu Holdings Ltd", "Giovanni Casu", "city_record", "confirmed", "active"),
    ]
