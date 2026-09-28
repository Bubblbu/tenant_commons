"""decode_fee (Long Term Rental fees read back into units, Licence By-law 4450, 2026 rates) and
licence_only_rentals (which licensed rentals become buildings of their own)."""

import pandas as pd
import polars as pl

from tc_core.prepare.buildings import licence_only_rentals
from tc_core.prepare.licence_fees import decode_fee


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def test_annual_dwelling_units():
    d = decode_fee(98.0)
    assert (d["fee_basis"], d["dwelling_units"], d["fee_certain"]) == ("annual", 1, True)
    assert decode_fee(30968.0)["dwelling_units"] == 316  # 1763 Comox St


def test_non_profit_flat_fee():
    d = decode_fee(277.0)
    assert d["non_profit"] and d["dwelling_units"] == 0


def test_prorated_non_profit_needs_the_subtype():
    # $77 + $277 x 9/12 = $284.75: a private $284 licence issued in April is not non-profit
    assert not decode_fee(284.0, ts("2026-04-18")).get("non_profit")
    # $77 + $277 x 7/12 = $238.58, issued late June
    assert decode_fee(239.0, ts("2026-06-29"), subtype="Non-Profit Housing")["non_profit"]


def test_new_licence_prorated_from_issue_month():
    d = decode_fee(126.0, ts("2026-07-15"))  # $77 + $98 x 6/12
    assert (d["fee_basis"], d["dwelling_units"]) == ("new, prorated", 1)
    d = decode_fee(142.0, ts("2026-05-10"))  # $77 + $98 x 8/12, not 2 housekeeping units
    assert (d["dwelling_units"], d["housekeeping_units"], d["fee_certain"]) == (1, 0, True)


def test_issue_month_may_trail_the_fee_by_one():
    # $77 + $98 x 10/12 = $158.67 (March), licence issued in April
    assert decode_fee(159.0, ts("2026-04-02"))["dwelling_units"] == 1


def test_pool():
    d = decode_fee(98.0 * 50 + 1108)
    assert (d["dwelling_units"], d["pool"]) == (50, 1)


def test_rooms_are_uncertain():
    d = decode_fee(145.0)  # $98 + $47: one dwelling unit and one sleeping unit, or something else
    assert (d["dwelling_units"], d["sleeping_units"], d["fee_certain"]) == (1, 1, False)


def test_special_amounts():
    assert decode_fee(237.0)["dwelling_units"] == 1
    assert decode_fee(77.0, status="Pending")["fee_basis"] == "application fee only (pending)"
    assert decode_fee(float("nan"))["fee_basis"] == "no fee"


# --- licence_only_rentals: which licensed rentals become buildings of their own ---

PROPS = pl.DataFrame({
    "address": ["1 a st", "3 a st", "5 a st", "7 a st", "9 a st", "11 a st", "855 burrard st",
                "13 a st", "21 a st", "35 a st"],
    "primary_address": ["1 a st", "1 a st", "5 a st", "7 a st", "9 a st", "11 a st", "855 burrard st",
                        "13 a st", "21 a st", "35 a st"],
})


def licences(*rows):
    return pl.DataFrame(
        [{"address": a, "feepaid": f, "issueddate": issued, "status": "Issued", "bsns_subtype": sub,
          "licencenumber": f"26-{i:06d}"}
         for i, (a, f, sub, issued) in enumerate(r if len(r) == 4 else (*r, None) for r in rows)],
        schema={"address": pl.Utf8, "feepaid": pl.Float64, "issueddate": pl.Utf8, "status": pl.Utf8,
                "bsns_subtype": pl.Utf8, "licencenumber": pl.Utf8},
    )


def test_licence_only_rentals_selection():
    out = licence_only_rentals(
        licences(
            ("3 a st", 98.0 * 40, None),          # same parcel as inventory building 1 a st
            ("5 a st", 98.0 * 40, None),          # new: 40 units
            ("7 a st", 98.0 * 3, None),           # too small
            ("7 a st", 98.0 * 2, None),           # ...even summed across licences (5 units): kept
            ("9 a st", 239.0, "Non-Profit Housing", "2026-06-29T15:23:09+00:00"),  # non-profit, prorated
            ("11 a st", 145.0 * 10, None),        # only readable with rooms: not counted
            ("99 nowhere st", 98.0 * 50, None),   # not a City address: dropped
            ("855 burrard st", 98.0 * 164, None),  # excluded (serviced suites)
            ("21 a st", 98.0 * 30, None),         # inventory building at 13 a st has 30 units: same one
            ("35 a st", 98.0 * 12, None),         # the 12-unit 61 a st is 26 numbers away: kept
        ),
        rental_units={"1 a st": 80, "13 a st": 30, "61 a st": 12},
        props=PROPS,
    )
    rows = {r["address"]: (r["units"], r["building_source"], r["source_licences"]) for r in out.iter_rows(named=True)}
    assert rows == {
        "5 a st": (40, "rental licence", "26-000001"),
        "7 a st": (5, "rental licence", "26-000002;26-000003"),  # every licence behind the count
        "9 a st": (None, "rental licence", "26-000004"),         # non-profit: no count, still traced
        "35 a st": (12, "rental licence", "26-000009"),
    }
