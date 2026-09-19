"""Guards the data/ layout: DataPaths is the single definition, and
config.toml's [paths] must agree with it (both are read by different code)."""

import tomllib
from pathlib import Path

from sica_core.paths import DataPaths

REPO_ROOT = Path(__file__).resolve().parent.parent

# config.toml [paths] key -> DataPaths attribute
CONFIG_KEYS = {
    "buildings": "buildings",
    "addresses": "property_addresses_csv",
    "blocks": "block_outlines_csv",
    "block_numbers": "block_numbers_csv",
    "local_area_boundary": "local_area_boundary_csv",
    "vtu": "vtu_public",
    "vtu_raw": "membership_full",
    "sica_core_db": "db",
    "pid_address_map": "pid_address_map",
    "sro_housing": "sro_housing",
    "rezoning_applications": "rezoning_applications",
    "coops": "coops",
    "ownership_claims": "ownership_claims",
    "lotr_ownership": "samwise_export",
}


def test_layout_stages():
    p = DataPaths("data")
    assert p.property_addresses_csv == Path("data/raw/cov_open_data/property-addresses.csv")
    assert p.cov("property-tax-report", "geojson") == Path(
        "data/raw/cov_open_data/property-tax-report.geojson"
    )
    assert p.ownership_claims == Path("data/curated/ownership_claims.csv")
    assert p.landlord_mapping == Path("data/curated/landlord_mapping.toml")
    assert p.all_rentals == Path("data/derived/interim/all_rentals.csv")
    assert p.buildings == Path("data/derived/buildings.csv")
    assert p.db == Path("data/derived/sica_core.db")


def test_root_is_configurable(tmp_path):
    p = DataPaths(tmp_path)
    assert p.buildings == tmp_path / "derived" / "buildings.csv"


def test_config_toml_matches_layout():
    cfg = tomllib.loads((REPO_ROOT / "config.toml").read_text())["paths"]
    p = DataPaths("data")
    for key, attr in CONFIG_KEYS.items():
        assert Path(cfg[key]) == getattr(p, attr), key
