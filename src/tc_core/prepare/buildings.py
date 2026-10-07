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
from ..normalize import AddressMatcher, addr_key_from_freeform
from .io import load_polars
from .licence_fees import decode_fee, parse_issued

PARCEL_SUMS = ("value_land", "value_bldg", "tax_levy")


def collapse_parcels(df: pl.DataFrame) -> pl.DataFrame:
    """One row per address from its property rows (one per pid/folio).

    A building can span several folios (air space parcels, consolidated lots):
    assessed values and tax are summed per distinct folio, pid/folio become
    sorted ";" lists, and every other column takes the first non-null value
    from the highest-value folio, so the row reads as one real parcel and the
    result doesn't depend on row order.
    """
    sums = [c for c in PARCEL_SUMS if c in df.columns]
    totals = (
        df.unique(["address", "folio", *sums])
        .group_by("address")
        .agg(pl.when(pl.col(c).is_not_null().any()).then(pl.col(c).sum()).alias(c) for c in sums)
    )
    value = pl.sum_horizontal(pl.col(c).fill_null(0) for c in sums if c != "tax_levy")
    by_value = dict(by=[value, pl.col("folio"), pl.col("pid")], descending=[True, False, False], nulls_last=True)
    rest = [c for c in df.columns if c not in ("address", "pid", "folio", *sums)]
    return (
        df.group_by("address")
        .agg(
            *(pl.col(c).sort_by(**by_value).drop_nulls().first() for c in rest),
            *(pl.col(c).drop_nulls().unique().sort().cast(pl.Utf8).str.join(";") for c in ("pid", "folio")),
        )
        .join(totals, on="address", how="left")
        .select(df.columns)
        .sort("address")
    )


BC_versions = {
    "B C": "BC",
    "B.C.": "BC",
}

# Licensed rentals the rental inventory doesn't list become buildings of their own when the
# fee pays for at least this many dwelling units (or the licence is for non-profit housing).
# Smaller licences are mostly one owner renting a suite, a condo or a house.
LICENCE_ONLY_MIN_UNITS = 5

# Licensed as Long Term Rental but not ordinary tenancies: furnished/serviced suites,
# retirement residences with care, hostels. Keyed by addr_key; reason kept for the record.
LICENCE_ONLY_EXCLUDED = {
    "855 burrard st": "Sutton Place Grande Residences: serviced suites attached to a hotel",
    "1128 alberni st": "Carmana Plaza: furnished hotel-style suites",
    "2799 yew st": "Seasons retirement residence",
    "1515 discovery st": "HI Vancouver Jericho Beach hostel",
    "1114 burnaby st": "HI Vancouver Downtown hostel",
}


def _civic_and_street(addr: str) -> tuple[int | None, str]:
    num, _, street = addr.partition(" ")
    return (int(num) if num.isdigit() else None), street


def licence_only_rentals(
    licences: pl.DataFrame, rental_units: dict[str, float | None], props: pl.DataFrame
) -> pl.DataFrame:
    """Current rental licences with no building in the rental inventory, as rental rows.

    `licences` needs address, feepaid, issueddate, status, bsns_subtype, licencenumber; `rental_units` maps
    each inventory address to its unit count. A licence counts as already on the map when its
    address, or any address on the same parcel (same primary_address in `props`), is an
    inventory address, or when an inventory building on the same street within 20 civic
    numbers has exactly the licensed unit count (one building on two parcels, e.g. 89 and
    97 W Georgia St). Units are the dwelling units its fee pays for (only readings without
    rooms, which are unambiguous); non-profit licences pay a flat fee and carry no unit count.
    Every row is marked building_source="rental licence", with the numbers of all current
    licences at its address in source_licences, so it can be traced back to the City's data.
    """
    primary_of = dict(props.select("address", "primary_address").unique("address").iter_rows())
    covered_parcels = {primary_of.get(a, a) for a in rental_units}
    units_by_street: dict[str, list[tuple[int, float]]] = {}
    for a, u in rental_units.items():
        num, street = _civic_and_street(a)
        if num is not None and u is not None:
            units_by_street.setdefault(street, []).append((num, u))

    def same_building_nearby(addr: str, units: int) -> bool:
        num, street = _civic_and_street(addr)
        return num is not None and any(
            abs(n - num) <= 20 and u == units for n, u in units_by_street.get(street, [])
        )

    rows = []
    cols = ("address", "feepaid", "issueddate", "status", "bsns_subtype", "licencenumber")
    for r in licences.select(cols).iter_rows(named=True):
        if not r["address"]:
            continue
        d = decode_fee(r["feepaid"], parse_issued(r["issueddate"]), r["status"], r["bsns_subtype"])
        rows.append({
            "address": r["address"],
            "dwelling_units": d.get("dwelling_units", 0) if d.get("fee_certain") else 0,
            "non_profit": bool(d.get("non_profit")),
            "licencenumber": r["licencenumber"],
        })
    if not rows:
        return pl.DataFrame(schema={"address": pl.Utf8, "units": pl.Int64, "building_source": pl.Utf8,
                                    "source_licences": pl.Utf8})
    per_address = (
        pl.DataFrame(rows)
        .group_by("address")
        .agg(
            pl.col("dwelling_units").sum(),
            pl.col("non_profit").any(),
            source_licences=pl.col("licencenumber").drop_nulls().unique().sort().str.join(";"),
        )
        .filter((pl.col("dwelling_units") >= LICENCE_ONLY_MIN_UNITS) | pl.col("non_profit"))
    )
    known = set(primary_of)
    keep = [
        a for a, units in per_address.select("address", "dwelling_units").iter_rows()
        if a in known
        and a not in rental_units
        and primary_of.get(a, a) not in covered_parcels
        and not same_building_nearby(a, units)
        and a not in LICENCE_ONLY_EXCLUDED
    ]
    return (
        per_address.filter(pl.col("address").is_in(keep))
        .select(
            "address",
            units=pl.when(pl.col("dwelling_units") > 0).then(pl.col("dwelling_units")).cast(pl.Int64),
            building_source=pl.lit("rental licence"),
            source_licences="source_licences",
        )
        .sort("address")
    )


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

    pl.Config.set_tbl_rows(10)

    # --- Datasets ---
    # pid is text (leading zeros; some aren't numeric, e.g. BCS1010): don't let
    # schema inference guess it from whichever rows happen to come first.
    props = pl.read_csv(properties_f, schema_overrides={"pid": pl.String})
    # Source addresses resolve to a property address (normalize.AddressMatcher:
    # ranges, unit prefixes, appended building names, missing street types),
    # falling back to the plain key so an unmatched row keeps its own address.
    matcher = AddressMatcher(props["address"].drop_nulls().to_list())
    to_key = lambda a: matcher.match(a) or addr_key_from_freeform(a)
    CLEAN = lambda col: pl.col(col).map_elements(to_key, return_dtype=pl.Utf8)

    # --- Chinatown properties ---
    ct_props = collapse_parcels(props.filter(pl.col("chinatown")))
    ct_props.write_csv(ct_properties_f)
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

    rentals = rentals.with_columns(_in_inventory=pl.lit(True)).join(
        nm_rentals.select("address", "name", "occupancy_year", "management", "units"),
        on="address",
        how="full",
        coalesce=True,
    ).with_columns(
        units=pl.when(pl.col("units").is_null())
        .then(pl.col("units_right"))
        .otherwise(pl.col("units")),
        # Which City list the building came from (licence-only rows below get "rental licence").
        building_source=pl.when(pl.col("_in_inventory"))
        .then(pl.lit("rental inventory"))
        .otherwise(pl.lit("non-market housing list")),
        year_built=pl.when(pl.col("year_built").is_null())
        .then(pl.col("occupancy_year"))
        .otherwise(pl.col("year_built")),
    )
    rentals = rentals.drop("_in_inventory")
    print("rentals + non-market:", rentals.shape)

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
            to_key, return_dtype=pl.Utf8
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

    # --- Licensed rentals the inventory doesn't list ---
    licence_only = licence_only_rentals(
        businesses, dict(rentals.select("address", "units").drop_nulls("address").iter_rows()), props
    )
    print(f"licence-only rentals added: {licence_only.height} "
          f"({int(licence_only['units'].sum() or 0)} units from licence fees)")
    rentals = pl.concat([rentals, licence_only], how="diagonal_relaxed")

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
        ).map_elements(to_key, return_dtype=pl.Utf8)
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
    buildings = collapse_parcels(buildings)

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
        "building_source",
        "source_licences",
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
    ).sort(["units", "address"], descending=[True, False], nulls_last=True)

    buildings.write_csv(buildings_f)
    print(f"buildings.csv: {buildings.height} rows -> {buildings_f}")
    n_with_secondary = buildings.filter(
        pl.col("secondary_addresses").is_not_null() & (pl.col("secondary_addresses") != "")
    ).height
    print(f"  ...of which {n_with_secondary} have at least one secondary address")

