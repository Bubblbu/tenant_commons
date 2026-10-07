import polars as pl

from tc_core.prepare.buildings import collapse_parcels


def _parcels(rows):
    return pl.DataFrame(
        rows,
        schema={
            "address": pl.String, "pid": pl.String, "folio": pl.Int64,
            "zoning_district": pl.String, "value_land": pl.Int64, "value_bldg": pl.Int64,
        },
        orient="row",
    )


# 179 Main St: a private company's remainder lot plus a non-profit's air space parcel.
AIR_SPACE = [
    ("179 main st", "030705452", 190579670000, "DEOD", 96100, 651000),
    ("179 main st", "029288231", 190579570000, "DEOD", 3690000, 12165000),
]


def test_values_are_summed_across_folios():
    row = collapse_parcels(_parcels(AIR_SPACE)).row(0, named=True)
    assert row["value_land"] == 3690000 + 96100
    assert row["value_bldg"] == 12165000 + 651000


def test_a_folio_with_several_pids_is_counted_once():
    rows = [
        ("1000 cypress st", "027677613", 624097080000, "RT-9", 13094000, 10000),
        ("1000 cypress st", "027677621", 624097080000, "RT-9", 13094000, 10000),
    ]
    row = collapse_parcels(_parcels(rows)).row(0, named=True)
    assert row["value_land"] == 13094000
    assert row["pid"] == "027677613;027677621"
    assert row["folio"] == "624097080000"


def test_parcel_columns_come_from_the_highest_value_folio():
    rows = [
        ("1010 pacific blvd", "025416511", 165606020000, "NOMINAL", 1, 1),
        ("1010 pacific blvd", "024264270", 165606040000, "CD-1 (324)", 4737000, 13867000),
    ]
    assert collapse_parcels(_parcels(rows))["zoning_district"].item() == "CD-1 (324)"


def test_output_does_not_depend_on_input_order():
    forward = collapse_parcels(_parcels(AIR_SPACE))
    backward = collapse_parcels(_parcels(AIR_SPACE[::-1]))
    assert forward.equals(backward)
    assert forward["pid"].item() == "029288231;030705452"
    assert forward["folio"].item() == "190579570000;190579670000"


def test_missing_values_stay_missing_rather_than_summing_to_zero():
    rows = [("388 slocan st", "031445721", None, None, None, None)]
    row = collapse_parcels(_parcels(rows)).row(0, named=True)
    assert row["value_land"] is None
    assert row["folio"] == ""
