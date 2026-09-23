"""Merge the 2023 (FOI 2023-186) and 2024 (FOI 2024-698) rental-market FOI
releases into one table, preferring the 2024 release wherever an address
appears in both (2024 has narrower coverage: 2,682 addresses vs 2023's
4,801, ~2,508 overlapping) and falling back to 2023 for the rest.

Ported from vhd's scripts/merge_foi_releases.py. Unlike the original, the
2023 input is the raw extract and the output is a separate file (the
original overwrote its own input, so a second run was not idempotent).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .address import clean_address

COMBINED_COLS = [
    "_norm_address",
    "Address",
    "Local_Area",
    "Current rental units",
    "Year built",
    "Current zoning",
    "Name",
    "Currentuse",
    "foi_release",
]


def merge_foi_releases(extract_2023: Path, extract_2024: Path, out: Path) -> int:
    # --- 2023 release (already in the pipeline schema) ---
    old = pl.read_csv(extract_2023).with_columns(
        _norm_address=pl.col("Address").map_elements(clean_address, return_dtype=pl.Utf8),
        foi_release=pl.lit("2023-186"),
    ).drop("id")

    # --- 2024 release (different schema: no Local_Area/Current zoning,
    # adds Name/Currentuse) ---
    new = pl.read_csv(extract_2024).rename(
        {
            "Address": "Address",
            "Total Rental Units": "Current rental units",
            "Year Built": "Year built",
        }
    ).with_columns(
        _norm_address=pl.col("Address").map_elements(clean_address, return_dtype=pl.Utf8),
        foi_release=pl.lit("2024-698"),
        **{
            "Local_Area": pl.lit(None, dtype=pl.Utf8),
            "Current zoning": pl.lit(None, dtype=pl.Utf8),
        },
    )

    # --- Merge: 2024 first so it wins the address-based de-dup ---
    old_aligned = old.with_columns(
        Name=pl.lit(None, dtype=pl.Utf8), Currentuse=pl.lit(None, dtype=pl.Utf8)
    ).select(COMBINED_COLS)
    new_aligned = new.select(COMBINED_COLS)

    merged = pl.concat([new_aligned, old_aligned]).unique(
        subset="_norm_address", keep="first"
    ).sort("_norm_address")
    n_2024 = merged.filter(pl.col("foi_release") == "2024-698").height
    n_2023 = merged.filter(pl.col("foi_release") == "2023-186").height
    print(
        f"Merged FOI releases: {merged.height} total addresses "
        f"({n_2024} from 2024-698, {n_2023} carried over from 2023-186 only)"
    )

    merged = merged.drop("_norm_address").with_row_index(name="id")
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.write_csv(out)
    return merged.height
