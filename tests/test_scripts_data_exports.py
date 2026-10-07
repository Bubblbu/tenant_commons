"""scripts/fetch_coops.py's normalize_coops() and
scripts/export_pid_address_map.py's build_pid_address_map() write CSVs the
pipeline reads (raw/chf_bc, derived/pid_address_map.csv)."""

import importlib.util
from pathlib import Path

import pytest

from tc_core.db import get_connection, init_db

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(df):
    rows = df.to_dicts() if hasattr(df, "to_dicts") else df.to_dict("records")
    # A missing value, however the frame spells it (the CSV writes it empty).
    return [{k: None if v != v else v for k, v in row.items()} for row in rows]


def _coop(title, city="Vancouver", **extra):
    return {
        "id": title.lower().replace(" ", "-"), "title": title,
        "location": {"city": city, "region": "Lower Mainland", "neighbourhood": "Kitsilano",
                     "school_district": "SD 39", "address_line": "1 Main St, Vancouver, BC"},
        "coordinates": [-123.1, 49.27], "status": "open_waitlist", "ownership_model": "non_profit",
        "bedrooms": [0, 3], "home_types": ["apartment", "townhouse"], "features": ["pets_ok"],
        **extra,
    }


def test_coops_are_flattened_filtered_to_the_city_and_sorted_by_title():
    rows = _rows(_script("fetch_coops").normalize_coops(
        [_coop("Zeta Co-op"), _coop("Burnaby Co-op", city="Burnaby"), _coop("Alpha Co-op")]
    ))
    assert [r["title"] for r in rows] == ["Alpha Co-op", "Zeta Co-op"]
    alpha = rows[0]
    assert (alpha["lat"], alpha["lon"]) == (49.27, -123.1)
    assert (alpha["bedrooms_min"], alpha["bedrooms_max"]) == (0, 3)
    assert alpha["home_types"] == "apartment;townhouse"
    assert alpha["address"] == "1 Main St, Vancouver, BC"


def test_a_coop_without_bedrooms_or_coordinates_keeps_them_empty():
    (row,) = _rows(_script("fetch_coops").normalize_coops([_coop("Bare Co-op", bedrooms=[], coordinates=None)]))
    assert row["bedrooms_min"] is None
    assert row["lat"] is None


def test_no_coops_in_the_city_fails_loudly():
    with pytest.raises(RuntimeError):
        _script("fetch_coops").normalize_coops([_coop("Burnaby Co-op", city="Burnaby")])


def _address_db(*points):
    conn = get_connection(":memory:")
    init_db(conn)
    conn.executemany(
        "INSERT INTO raw_addresses (p_parcel_id, site_id, civic_number, std_street, geo_local_area, "
        "geo_point_2d, ingested_at) VALUES (?, ?, ?, ?, ?, ?, 'now')",
        points,
    )
    return conn


def test_pid_map_keeps_only_real_pids_and_sorts_by_address_key():
    conn = _address_db(
        ("P2", "015666808", "1924", "W 4TH AV", "Kitsilano", "49.27, -123.15"),
        ("P1", "BCS1010", "100", "MAIN ST", "Strathcona", "49.28, -123.10"),
        ("P3", None, None, "OAK ST", "Fairview", None),
    )
    rows = _rows(_script("export_pid_address_map").build_pid_address_map(conn))
    assert [r["address_point_id"] for r in rows] == ["P1", "P2", "P3"]
    main, fourth, oak = rows
    assert (main["pid"], main["address"], main["addr_key"]) == (None, "100 MAIN ST", "100 main st")
    assert (fourth["pid"], fourth["address"], fourth["local_area"]) == ("015666808", "1924 W 4TH AV", "Kitsilano")
    assert (oak["address"], oak["lat_lon"]) == ("OAK ST", None)


def test_pid_map_rejects_duplicate_address_points():
    conn = _address_db(
        ("P1", "015666808", "1", "MAIN ST", "Strathcona", None),
        ("P1", "015666809", "2", "MAIN ST", "Strathcona", None),
    )
    with pytest.raises(RuntimeError):
        _script("export_pid_address_map").build_pid_address_map(conn)
