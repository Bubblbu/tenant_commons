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


def test_a_building_name_in_the_2024_address_moves_to_name_and_2024_still_wins(tmp_path):
    # The 2024 extract appends the building name to the address ("1005 JERVIS
    # ST Mathew Court"); keyed as-is it never matched its 2023 row, so both
    # survived and the older 2023 row won downstream.
    f2023 = tmp_path / "2023.csv"
    f2023.write_text(
        "id,Address,Local_Area,Current rental units,Year built,Current zoning\n"
        "0,1005 JERVIS ST,West End,130,1974,RM-5\n"
    )
    f2024 = tmp_path / "2024.csv"
    f2024.write_text(
        "Address,Total Rental Units,Year Built,Name,Currentuse\n"
        "1005 JERVIS ST Mathew Court,136,1974,,Pb-Rental\n"
    )
    out = tmp_path / "all_rentals.csv"

    assert merge_foi_releases(f2023, f2024, out) == 1
    row = pl.read_csv(out).row(0, named=True)
    assert row["foi_release"] == "2024-698"
    assert row["Address"] == "1005 JERVIS ST"
    assert row["Name"] == "Mathew Court"
    assert row["Current rental units"] == 136


def test_an_existing_name_is_kept(tmp_path):
    f2023 = tmp_path / "2023.csv"
    f2023.write_text(
        "id,Address,Local_Area,Current rental units,Year built,Current zoning\n"
        "0,200 Oak Street,Kitsilano,5,1960,RM-4\n"
    )
    f2024 = tmp_path / "2024.csv"
    f2024.write_text(
        "Address,Total Rental Units,Year Built,Name,Currentuse\n"
        "1005 JERVIS ST Mathew Court,136,1974,The Mathew,Pb-Rental\n"
    )
    out = tmp_path / "all_rentals.csv"
    merge_foi_releases(f2023, f2024, out)
    row = pl.read_csv(out).filter(pl.col("Address").str.contains("JERVIS")).row(0, named=True)
    assert row["Address"] == "1005 JERVIS ST"
    assert row["Name"] == "The Mathew"
