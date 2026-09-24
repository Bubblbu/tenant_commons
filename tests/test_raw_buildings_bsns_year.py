"""buildings.csv carries the business-licence data year (bsns_year) that the
export publishes as filter_config.licence_year."""

from tc_core.db import get_connection, init_db
from tc_core.ingest.raw_buildings import ingest_raw_buildings


def test_bsns_year_is_ingested(tmp_path):
    path = tmp_path / "buildings.csv"
    path.write_text("address,local_area,bsns_group,bsns_year\n100 main st,Downtown,X Ltd,2026\n")
    conn = get_connection(":memory:")
    init_db(conn)

    assert ingest_raw_buildings(conn, str(path)) == 1
    assert conn.execute("SELECT bsns_year FROM raw_buildings").fetchone()[0] == 2026
