"""Primary-address resolution and licence matching in tc_core.prepare.

The case behind these tests: 512 Campbell Ave (Stamp's Place) is a "Main"
VanMaps address on the 500 Campbell Ave parcel (PID 030-450-098). Its rental
licence is filed at 500, and the registry filing is against that PID, so
treating 512 as its own primary address left the building with no PID and
no owner.
"""

import polars as pl

from tc_core.prepare.buildings import attach_licences
from tc_core.prepare.properties import attach_property_records, resolve_primary_address


def _vanmaps(rows):
    return pl.DataFrame(
        rows,
        schema=[
            "civic_number",
            "std_street",
            "civic_number_primary",
            "std_street_primary",
            "address_type",
        ],
        orient="row",
    )


def test_main_address_on_another_primary_resolves_to_that_primary():
    out = resolve_primary_address(
        _vanmaps([("512", "CAMPBELL AV", "500", "CAMPBELL AV", "Main")])
    )
    assert out.select("address", "primary_address").row(0) == (
        "512 campbell ave",
        "500 campbell ave",
    )


def test_secondary_address_resolves_to_its_primary():
    out = resolve_primary_address(
        _vanmaps([("429", "RAYMUR AV", "500", "CAMPBELL AV", "Secondary")])
    )
    assert out["primary_address"].to_list() == ["500 campbell ave"]


def test_address_without_a_recorded_primary_is_its_own_primary():
    out = resolve_primary_address(
        _vanmaps([("1650", "HARO ST", None, None, "Main")])
    )
    assert out["primary_address"].to_list() == ["1650 haro st"]


def _pids_by_address(addresses, properties):
    out = attach_property_records(
        pl.DataFrame(addresses, schema=["address", "primary_address"], orient="row"),
        pl.DataFrame(properties, schema=["address", "pid"], orient="row"),
    )
    return {
        a: sorted(p for p in out.filter(pl.col("address") == a)["pid"].to_list() if p)
        for a in out["address"].unique()
    }


def test_address_without_its_own_pid_takes_its_primary_pid():
    pids = _pids_by_address(
        [("512 campbell ave", "500 campbell ave")], [("500 campbell ave", "030450098")]
    )
    assert pids == {"512 campbell ave": ["030450098"]}


def test_address_with_its_own_pid_keeps_it_over_its_primary():
    # 53 W Cordova St has its own address point (and parcel), although
    # VanMaps names 23 W Cordova St as its primary.
    pids = _pids_by_address(
        [("53 w cordova st", "23 w cordova st")],
        [
            ("53 w cordova st", "032861320"),
            ("23 w cordova st", "030395534"),
            ("23 w cordova st", "032861338"),
        ],
    )
    assert pids == {"53 w cordova st": ["032861320"]}


def test_address_whose_primary_has_no_pid_keeps_its_own():
    pids = _pids_by_address(
        [("3030 kingsway", "3036 kingsway")], [("3030 kingsway", "032107765")]
    )
    assert pids == {"3030 kingsway": ["032107765"]}


def _licences(rows):
    return pl.DataFrame(rows, schema=["address", "bsns_name"], orient="row")


def test_building_without_its_own_licence_takes_its_primary_address_licence():
    housing = pl.DataFrame(
        {"address": ["512 campbell ave"], "primary_address": ["500 campbell ave"]}
    )
    out = attach_licences(housing, _licences([("500 campbell ave", "New Chelsea Society")]))
    assert out["bsns_name"].to_list() == ["New Chelsea Society"]


def test_building_own_licence_wins_over_its_primary_address_licence():
    housing = pl.DataFrame(
        {"address": ["512 campbell ave"], "primary_address": ["500 campbell ave"]}
    )
    out = attach_licences(
        housing,
        _licences(
            [("512 campbell ave", "Own Licensee"), ("500 campbell ave", "Parcel Licensee")]
        ),
    )
    assert out["bsns_name"].to_list() == ["Own Licensee"]


def test_building_with_no_licence_anywhere_stays_unlicensed():
    housing = pl.DataFrame({"address": ["1 nowhere st"], "primary_address": ["1 nowhere st"]})
    out = attach_licences(housing, _licences([("500 campbell ave", "New Chelsea Society")]))
    assert out.height == 1
    assert out["bsns_name"].to_list() == [None]
