"""Open Data added a `note` column to property-addresses; it must be kept."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sica_core.db import get_connection, init_db
from sica_core.ingest.raw_addresses import ingest_raw_addresses, load_raw_addresses_frame

NOTE = "Translated name until colonial systems support multi-lingual characters."
HEADER = "civic_number;geo_local_area;geom;p_parcel_id;pcoord;site_id;std_street;note;geo_point_2d"


def _csv(tmp_path: Path) -> str:
    p = tmp_path / "property-addresses.csv"
    p.write_text(
        HEADER + "\n"
        f"100;West End;;P1;C1;S1;MAIN ST;{NOTE};49.28, -123.13\n"
        "200;West End;;P2;C2;S2;OAK ST;;49.29, -123.14\n",
        encoding="utf-8",
    )
    return str(p)


def test_frame_includes_note(tmp_path):
    df = load_raw_addresses_frame(_csv(tmp_path))
    assert "note" in df.columns


def test_ingest_stores_note_and_null(tmp_path):
    conn = get_connection(":memory:")
    init_db(conn)
    assert ingest_raw_addresses(conn, _csv(tmp_path)) == 2
    got = dict(conn.execute("SELECT civic_number, note FROM raw_addresses").fetchall())
    assert got["100"] == NOTE
    assert got["200"] is None
