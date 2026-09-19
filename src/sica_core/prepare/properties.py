"""Rebuild derived/interim/properties.csv from the raw Open Data files.

Ported from vhd's scripts/build_properties.py (logic unchanged). Includes the
VanMaps primary/secondary address resolution (raw/vanmaps/addresses.geojson)
and the Chinatown boundary flag (curated/chinatown_boundary.geojson).

Note on the Chinatown boundary: only one boundary file survives, an
"expanded" one. The original notebooks distinguished a narrower
`boundaries.shp` from a wider `ct_ext.shp`, so `chinatown=True` here may
cover more addresses than the original ~161-row baseline did.

Differences from the vhd script: paths come from DataPaths, clean_address and
fix_street_names are imported, and the one-off `properties.pre-refresh.csv`
backup is gone (derived files are regenerable).
"""

from __future__ import annotations

import geopandas
import polars as pl

from ..paths import DataPaths
from .address import clean_address, fix_street_names
from .io import load_polars


def run(paths: DataPaths) -> None:
    addresses_f = paths.vanmaps_addresses
    property_addresses_f = paths.cov("property-addresses", "geojson")
    property_tax_f = paths.cov("property-tax-report", "geojson")
    chinatown_boundary_f = paths.chinatown_boundary
    properties_f = paths.properties
    properties_f.parent.mkdir(parents=True, exist_ok=True)

    # --- addresses.geojson: VanMaps primary/secondary address resolution ---
    print("Loading addresses.geojson (VanMaps) ...")
    addresses = load_polars(addresses_f)
    addresses = addresses.with_columns(
        address=pl.concat_str(
            pl.col("civic_number"), pl.lit(" "), pl.col("std_street")
        ).map_elements(clean_address, return_dtype=pl.Utf8),
    ).with_columns(
        primary_address=pl.when(pl.col("address_type") == "Secondary")
        .then(
            pl.concat_str(
                pl.col("civic_number_primary"),
                pl.lit(" "),
                pl.col("std_street_primary"),
            )
        )
        .otherwise(pl.col("address"))
        .map_elements(clean_address, return_dtype=pl.Utf8)
    )
    addresses = addresses.select(
        "objectid",
        "propertyviewerid",
        "address",
        "primary_address",
        "address_type",
        "address_status",
    )
    print("VanMaps addresses:", addresses.height)

    # --- property-addresses.geojson: base address/pid list ---
    print("Loading property-addresses.geojson ...")
    properties = load_polars(property_addresses_f)
    print("Raw entries:", properties.height)

    properties = properties.with_columns(
        address=pl.concat_str(
            pl.col("civic_number"), pl.lit(" "), pl.col("std_street")
        ).map_elements(clean_address, return_dtype=pl.Utf8),
        pid=pl.col("site_id"),
    )
    properties = properties.drop_nulls(subset="address")
    print("After dropping null addresses:", properties.height)

    properties = properties.drop(
        ["civic_number", "std_street", "p_parcel_id", "pcoord", "geo_point_2d", "site_id"]
    )

    # Join VanMaps addresses (primary/secondary resolution) against the
    # property-addresses PID list, keyed on primary_address.
    props = (
        addresses.select("address", "primary_address", "address_type", "address_status")
        .join(properties, left_on="primary_address", right_on="address", how="left")
        .unique()
    )
    print("props after VanMaps join:", props.height)

    # --- Chinatown boundary flag ---
    print("Loading Chinatown boundary ...")
    addr_gdf = geopandas.read_file(property_addresses_f)
    ct_boundary = geopandas.read_file(chinatown_boundary_f)
    addr_gdf["chinatown"] = addr_gdf["geometry"].within(ct_boundary.iloc[0]["geometry"])

    ct = pl.from_pandas(
        addr_gdf.loc[addr_gdf["chinatown"], ["civic_number", "std_street", "chinatown"]]
    )
    ct = ct.with_columns(
        address=pl.concat_str(
            pl.col("civic_number"), pl.lit(" "), pl.col("std_street")
        ).map_elements(clean_address, return_dtype=pl.Utf8),
    ).select("address", "chinatown")
    print("Addresses within Chinatown boundary:", ct.height)

    props = props.join(ct, on="address", how="left").unique()
    props = props.with_columns(pl.col("chinatown").fill_null(False))

    # --- property-tax-report.geojson: assessment values ---
    print("Loading property-tax-report.geojson ...")
    keep_cols = [
        "pid",
        "address",
        "folio",
        "zoning_district",
        "zoning_classification",
        "current_land_value",
        "current_improvement_value",
        "tax_levy",
    ]

    prop_assess = load_polars(property_tax_f)
    prop_assess = prop_assess.with_columns(
        pl.col("street_name").map_elements(fix_street_names, return_dtype=pl.Utf8),
        pl.col("pid").str.replace_all("-", ""),
    ).with_columns(
        address=pl.concat_str(
            pl.col("to_civic_number"), pl.lit(" "), pl.col("street_name")
        ).map_elements(clean_address, return_dtype=pl.Utf8)
    )

    prop_assess = prop_assess.filter(pl.col("legal_type") == "LAND")
    prop_assess = prop_assess.filter(pl.col("pid").is_not_null())
    prop_assess = prop_assess.select(keep_cols).rename(
        {"current_land_value": "value_land", "current_improvement_value": "value_bldg"}
    )
    print("Property tax (LAND) rows:", prop_assess.height)

    props = props.join(
        prop_assess,
        left_on=["primary_address", "pid"],
        right_on=["address", "pid"],
        how="left",
    ).unique()

    props = props.select(
        "pid",
        "folio",
        "address",
        "primary_address",
        "geo_local_area",
        "chinatown",
        "address_type",
        "address_status",
        "zoning_district",
        "zoning_classification",
        "value_land",
        "value_bldg",
        "tax_levy",
    )

    props.write_csv(properties_f)
    print(f"Wrote {props.height} rows -> {properties_f}")
