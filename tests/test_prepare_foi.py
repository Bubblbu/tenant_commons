import polars as pl

from tc_core.prepare.foi import merge_foi_releases


def _write_inputs(tmp_path):
    f2023 = tmp_path / "2023.csv"
    f2023.write_text(
        "id,Address,Local_Area,Current rental units,Year built,Current zoning\n"
        "0,100 Main Street,Downtown Eastside,10,1950,RM-4\n"
        "1,200 Oak Street,Kitsilano,5,1960,RM-4\n"
    )
    f2024 = tmp_path / "2024.csv"
    f2024.write_text(
        "Address,Total Rental Units,Year Built,Name,Currentuse\n"
        "100 Main St,12,1951,Main House,Apartment\n"
    )
    return f2023, f2024


def test_2024_wins_on_overlap_and_2023_fills_gaps(tmp_path):
    f2023, f2024 = _write_inputs(tmp_path)
    out = tmp_path / "interim" / "all_rentals.csv"

    n = merge_foi_releases(f2023, f2024, out)

    df = pl.read_csv(out)
    assert n == df.height == 2
    main = df.filter(pl.col("Address").str.contains("Main")).row(0, named=True)
    assert main["foi_release"] == "2024-698"
    assert main["Current rental units"] == 12
    oak = df.filter(pl.col("Address").str.contains("Oak")).row(0, named=True)
    assert oak["foi_release"] == "2023-186"


def test_is_idempotent(tmp_path):
    f2023, f2024 = _write_inputs(tmp_path)
    out = tmp_path / "all_rentals.csv"
    merge_foi_releases(f2023, f2024, out)
    first = pl.read_csv(out).sort("Address")
    merge_foi_releases(f2023, f2024, out)
    assert pl.read_csv(out).sort("Address").equals(first)
