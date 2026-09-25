"""Rebuild derived/buildings.csv (one row per building, with landlord
attribution) and derived/ct_properties.csv from refreshed inputs.

Ported from vhd's scripts/build_buildings.py (logic unchanged: address
cleaning, the FOI/non-market/issues joins, the `Long-term Rental` business
licence filter, and the
`secondary_addresses` column), except that licensees keep their filed names
(no curated/landlord_mapping.toml renaming; see ownership_claims). Removed: the writes of rental_properties.csv,
nm_rental_properties.csv, address_index.csv and landlord_summary.csv, which
nothing in this repo reads. vhd's own docstring records why the notebook
logic was reconstructed the way it was (the undefined `addresses` variable,
the retired Google Sheets push); that history stays in the archive.
"""

from __future__ import annotations

import polars as pl
import polars.selectors as cs

from ..paths import DataPaths
from ..normalize import addr_key_from_freeform
from .io import load_polars

BC_versions = {
    "B C": "BC",
    "B.C.": "BC",
}


def attach_licences(housing: pl.DataFrame, bsns_by_address: pl.DataFrame) -> pl.DataFrame:
    """Left-join per-address licence columns onto housing rows.

    A building's own address wins. A building with no licence there takes
    the licence filed at its parcel's primary address: Stamp's Place is
    listed at 512 Campbell Ave, but its rental licence is filed at 500
    Campbell Ave, the parcel's primary. `bsns_by_address` must be one row
    per address, so neither join adds rows.
    """
    licence_cols = [c for c in bsns_by_address.columns if c != "address"]
    by_primary = bsns_by_address.rename(
        {"address": "primary_address", **{c: f"{c}__primary" for c in licence_cols}}
    )
    has_own = pl.any_horizontal([pl.col(c).is_not_null() for c in licence_cols])
    return (
        housing.join(bsns_by_address, on="address", how="left")
        .join(by_primary, on="primary_address", how="left")
        .with_columns(
            [
                pl.when(has_own).then(pl.col(c)).otherwise(pl.col(f"{c}__primary")).alias(c)
                for c in licence_cols
            ]
        )
        .drop([f"{c}__primary" for c in licence_cols])
    )


def run(paths: DataPaths) -> None:
    properties_f = paths.properties
    all_rentals_f = paths.all_rentals
    business_licenses_f = paths.cov("business-licences", "geojson")
    non_market_housing_f = paths.cov("non-market-housing", "geojson")
    rental_standards_issues_f = paths.cov("rental-standards-current-issues", "geojson")
    buildings_f = paths.buildings
    ct_properties_f = paths.ct_properties
    buildings_f.parent.mkdir(parents=True, exist_ok=True)

    CLEAN = lambda col: pl.col(col).map_elements(addr_key_from_freeform, return_dtype=pl.Utf8)

    pl.Config.set_tbl_rows(10)

    # --- Datasets ---
    props = pl.read_csv(properties_f)

    # --- Chinatown properties ---
    ct_props = (
        props.filter(pl.col("chinatown"))
        .group_by("address")
        .agg(pl.all().drop_nulls().unique())
        .with_columns(pl.exclude("address", "pid", "folio").list.first())
    )
    ct_props.with_columns(
        pl.col("pid", "folio").cast(pl.List(pl.Utf8)).list.join(";")
    ).write_csv(ct_properties_f)
    print(f"ct_properties.csv: {ct_props.height} rows")

    # --- Rentals (merged FOI 2023+2024, see tc_core.prepare.foi) ---
    rentals = pl.read_csv(all_rentals_f)
    rentals = rentals.rename(
        {
            "Address": "address",
            "Local_Area": "local_area",
            "Current rental units": "units",
            "Year built": "year_built",
            "Current zoning": "zoning",
            "Name": "foi_name",
        }
    ).with_columns(address=CLEAN("address"))
    rentals = rentals.unique(subset="address", keep="first").drop("id")
    print("rentals:", rentals.shape)

    # --- Non-market housing ---
    nm_rentals = load_polars(non_market_housing_f)
    nm_rentals = nm_rentals.with_columns(
        address=CLEAN("address"),
        units=pl.sum_horizontal(cs.contains("clientele")),
    ).select(
        "name",
        "address",
        "project_status",
        "occupancy_year",
        "units",
        pl.col("operator").alias("management"),
    )
    nm_rentals = nm_rentals.filter(pl.col("project_status") == "Completed")
    nm_rentals = nm_rentals.sort("occupancy_year").unique(subset="address", keep="last")
    print("nm_rentals:", nm_rentals.shape)

    rentals = rentals.join(
        nm_rentals.select("address", "name", "occupancy_year", "management", "units"),
        on="address",
        how="full",
        coalesce=True,
    ).with_columns(
        units=pl.when(pl.col("units").is_null())
        .then(pl.col("units_right"))
        .otherwise(pl.col("units")),
        year_built=pl.when(pl.col("year_built").is_null())
        .then(pl.col("occupancy_year"))
        .otherwise(pl.col("year_built")),
    )
    print("rentals + non-market:", rentals.shape)

    # --- Join with property information ---
    # NOTE: reconstructs the notebook's undefined `addresses` reference (history
    # is in the archived vhd scripts) using `props` with geo_local_area -> local_area.
    addresses_for_join = props.rename({"geo_local_area": "local_area"})
    housing = (
        rentals.drop("units_right", "occupancy_year")
        .join(addresses_for_join, on="address", how="inner")
        .with_columns(
            local_area=pl.when(pl.col("local_area").is_null())
            .then(pl.col("local_area_right"))
            .otherwise(pl.col("local_area")),
        )
        .drop("local_area_right")
    )
    print("housing (after property join):", housing.shape)

    # --- Ongoing rental-standards issues ---
    issues = load_polars(rental_standards_issues_f)
    issues = issues.with_columns(
        address=pl.concat_str(
            pl.col("streetnumber"), pl.lit(" "), pl.col("street")
        ).map_elements(addr_key_from_freeform, return_dtype=pl.Utf8)
    )
    housing = housing.join(
        issues.select(
            "address",
            pl.col("totaloutstanding").alias("n_issues"),
            pl.col("detailurl").alias("issues_details"),
        ),
        on="address",
        how="left",
    )
    print("housing (after issues join):", housing.shape)

    # --- Businesses ---
    # bsns_group is the licensee as filed. It used to be renamed through
    # curated/landlord_mapping.toml; those groupings now live in
    # ownership_claims (same_entity / common_owner / managed_by), so each
    # company keeps its own name and the claims group it.
    businesses = load_polars(business_licenses_f)
    latest_year = businesses.select(pl.col("folderyear").cast(pl.Int32).max()).item()
    print(f"Using latest business-licence folderyear: {latest_year}")
    # The City publishes folderyear as two digits ("26").
    licence_year = latest_year if latest_year >= 1000 else 2000 + latest_year
    businesses = businesses.filter(pl.col("folderyear") == str(latest_year))

    businesses = businesses.with_columns(
        address=pl.concat_str(pl.col("house"), pl.lit(" "), pl.col("street")).map_elements(
            addr_key_from_freeform, return_dtype=pl.Utf8
        ),
    )
    businesses = businesses.with_columns(
        "address",
        bsns_group=pl.col("businessname").replace(BC_versions),
        bsns_name=pl.col("businessname"),
        bsns_trade_name="businesstradename",
        bsns_type="businesstype",
        bsns_subtype="businesssubtype",
    )
    # NOTE: Vancouver overhauled its business-licence category taxonomy since
    # vhd.business_mappings.valid_business_types was written -- none of those
    # old categories ("Apartment House", "Multiple Dwelling", "Duplex", "Rooming
    # House", ...) exist anymore. "Long-term Rental" is the current closest
    # equivalent (confirmed with the user). `businesssubtype` partially preserves
    # some of the old granularity (e.g. "Non-Profit Housing", "Multiple Dwelling
    # - 99 Year Lease") but is null for the large majority of rows (15,542 of
    # 15,913) -- it is NOT a full replacement for the retired category list, and
    # is carried through as bsns_subtype below on a best-effort basis.
    businesses = businesses.filter(pl.col("bsns_type") == "Long-term Rental")
    businesses = businesses.filter(pl.col("status").is_in(["Issued", "Pending"]))
    print("businesses (housing-related, active licences):", businesses.shape)

    # --- Per-building index WITH landlord attribution (buildings.csv) ---
    # (History of this step lives in the archived vhd scripts.)
    bsns_by_address = businesses.group_by("address").agg(
        bsns_group=pl.col("bsns_group").unique().drop_nulls(),
        bsns_name=pl.col("bsns_name").unique().drop_nulls(),
        bsns_trade_name=pl.col("bsns_trade_name").unique().drop_nulls(),
        bsns_type=pl.col("bsns_type").unique().drop_nulls(),
        bsns_subtype=pl.col("bsns_subtype").unique().drop_nulls(),
    )

    buildings = attach_licences(housing, bsns_by_address).with_columns(
        cs.by_dtype(pl.List(pl.Utf8)).list.join(";")
    )

    # Collapse to one row per address (the VanMaps join can bring in multiple
    # pid/objectid records per primary_address).
    buildings = (
        buildings.group_by("address")
        .agg(pl.all().drop_nulls().unique())
        .with_columns(pl.exclude("address", "pid", "folio").list.first())
        .with_columns(pl.col("pid", "folio").cast(pl.List(pl.Utf8)).list.join(";"))
    )

    # --- Address lookup: every address (primary + secondary) VanMaps knows
    # about, resolved to its primary address and property. Folded into buildings.csv
    # as `secondary_addresses` (the standalone address_index.csv is no longer
    # written), so a building's alternate civic addresses are
    # visible without a separate lookup.

    alias_groups = (
        props.select("address", "primary_address")
        .unique()
        .group_by("primary_address")
        .agg(pl.col("address").sort().alias("_all_addresses"))
    )

    buildings = buildings.join(alias_groups, on="primary_address", how="left").with_columns(
        secondary_addresses=pl.struct(["address", "_all_addresses"]).map_elements(
            lambda s: ";".join(
                a for a in (s["_all_addresses"] or []) if a != s["address"]
            ),
            return_dtype=pl.Utf8,
        )
    ).drop("_all_addresses")

    buildings = buildings.with_columns(bsns_year=pl.lit(licence_year))
    buildings = buildings.select(
        "address",
        "secondary_addresses",
        "local_area",
        "primary_address",
        "pid",
        "folio",
        "units",
        "year_built",
        "zoning",
        "zoning_district",
        "zoning_classification",
        "value_land",
        "value_bldg",
        "bsns_group",
        "bsns_name",
        "bsns_trade_name",
        "bsns_type",
        "bsns_subtype",
        "bsns_year",
        "name",
        "foi_name",
        "management",
        "n_issues",
        "issues_details",
    ).sort("units", descending=True, nulls_last=True)

    buildings.write_csv(buildings_f)
    print(f"buildings.csv: {buildings.height} rows -> {buildings_f}")
    n_with_secondary = buildings.filter(
        pl.col("secondary_addresses").is_not_null() & (pl.col("secondary_addresses") != "")
    ).height
    print(f"  ...of which {n_with_secondary} have at least one secondary address")

