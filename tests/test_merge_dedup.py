"""merge_and_dedupe_buildings() collapses raw_buildings rows sharing an
address key into one building. Which value wins matters: it sets what the
map shows, and output order sets building_id."""

from tc_core.db import get_connection, init_db
from tc_core.ingest.merge import load_raw_frames, merge_and_dedupe_buildings

NOW = "2026-10-06T00:00:00+00:00"


def _conn(*buildings):
    conn = get_connection(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_addresses (civic_number, std_street, geo_point_2d, geo_local_area, ingested_at) "
        "VALUES ('100', 'MAIN ST', '49.28, -123.10', 'Strathcona', ?), "
        "('200', 'OAK ST', '49.26, -123.12', 'Fairview', ?)",
        (NOW, NOW),
    )
    for b in buildings:
        cols = ", ".join([*b, "ingested_at"])
        conn.execute(
            f"INSERT INTO raw_buildings ({cols}) VALUES ({', '.join('?' * (len(b) + 1))})",
            (*b.values(), NOW),
        )
    return conn


def _merged(conn):
    out = merge_and_dedupe_buildings(*load_raw_frames(conn))
    return out.to_dicts() if hasattr(out, "to_dicts") else out.to_dict("records")


def test_tied_values_resolve_to_the_alphabetically_first():
    conn = _conn(
        {"address": "100 Main St", "local_area": "Strathcona", "bsns_group": "Zeta Holdings Ltd"},
        {"address": "100 MAIN ST", "local_area": "Strathcona", "bsns_group": "Alpha Holdings Ltd"},
    )
    (building,) = _merged(conn)
    assert building["address"] == "100 MAIN ST"
    assert building["owner_group"] == "Alpha Holdings Ltd"


def test_the_most_common_value_wins_over_alphabetical_order():
    conn = _conn(
        {"address": "100 main st", "bsns_group": "Zeta Holdings Ltd"},
        {"address": "100 main st", "bsns_group": "Zeta Holdings Ltd"},
        {"address": "100 main st", "bsns_group": "Alpha Holdings Ltd"},
    )
    assert _merged(conn)[0]["owner_group"] == "Zeta Holdings Ltd"


def test_year_built_is_the_median_and_units_the_maximum():
    conn = _conn(
        {"address": "100 main st", "year_built": 1950, "units": 10},
        {"address": "100 main st", "year_built": 1961, "units": 12},
    )
    (building,) = _merged(conn)
    assert building["year_built"] == 1955.5
    assert building["units"] == 12


def test_issue_details_come_from_the_row_with_the_most_issues():
    conn = _conn(
        {"address": "100 main st", "n_issues": 1, "issues_details": "https://example.org/one"},
        {"address": "100 main st", "n_issues": 4, "issues_details": "https://example.org/four"},
    )
    (building,) = _merged(conn)
    assert (building["n_issues"], building["issues_details"]) == (4, "https://example.org/four")


def test_a_city_list_beats_a_licence():
    conn = _conn(
        {"address": "100 main st", "building_source": "rental licence"},
        {"address": "100 main st", "building_source": "rental inventory"},
    )
    assert _merged(conn)[0]["building_source"] == "rental inventory"


def test_buildings_come_out_in_first_appearance_order():
    conn = _conn(
        {"address": "200 oak st"},
        {"address": "100 main st"},
        {"address": "200 oak st"},
    )
    assert [b["addr_key"] for b in _merged(conn)] == ["200 oak st", "100 main st"]
