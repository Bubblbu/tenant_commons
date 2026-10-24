"""Raw sources for building housing facts (spec 2026-10-20, housing type):
the 2024 rental licences by building type and the non-market list's
clientele and operator, stored verbatim."""

from __future__ import annotations

import json

from tc_core.db import get_connection, init_db
from tc_core.ingest.raw_housing_sources import ingest_raw_licences_2024, ingest_raw_non_market


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def test_2024_licences_are_stored_verbatim(tmp_path):
    src = tmp_path / "business-licences-2013-to-2024.csv"
    src.write_text(
        "﻿licencenumber;status;businesstype;house;street;geo_point_2d\n"
        "24-179204;Inactive;Apartment House *Historic*;3023;QUEBEC ST;49.258, -123.103\n"
        "24-100001;Cancelled;Rooming House *Historic*;10;MAIN ST;\n",
        encoding="utf-8",
    )
    conn = _conn()
    assert ingest_raw_licences_2024(conn, str(src)) == 2
    assert conn.execute("SELECT licencenumber, businesstype, house, street FROM raw_licences_2024 "
                        "ORDER BY 1").fetchall()[1] == ("24-179204", "Apartment House *Historic*", "3023", "QUEBEC ST")


def test_non_market_clientele_and_operator_are_stored(tmp_path):
    src = tmp_path / "non-market-housing.geojson"
    src.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": None, "properties": {
            "index_number": 6, "name": "Helen's Court Co-op", "address": "2137 W 1st Ave",
            "project_status": "Completed", "occupancy_year": "1984",
            "operator": "Helen's Court Co-op Housing Association", "clientele_families": 35,
            "clientele_seniors": 0, "clientele_other": 9, "design_standard_1br": 7, "url": "https://x"}},
    ]}), encoding="utf-8")
    conn = _conn()
    assert ingest_raw_non_market(conn, str(src)) == 1
    assert conn.execute("SELECT index_number, address, operator, clientele_families, clientele_seniors, "
                        "clientele_other FROM raw_non_market").fetchone() == (
        "6", "2137 W 1st Ave", "Helen's Court Co-op Housing Association", 35, 0, 9)
