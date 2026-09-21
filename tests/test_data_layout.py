"""Guards the data/ layout: DataPaths is the single definition, and
config.toml's [paths] must agree with it (both are read by different code)."""

import ast
import tomllib
from pathlib import Path

from sica_core.config import DEFAULT_ARTIFACTS_DIR, DEFAULT_DB_PATH
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
    "artifacts": "artifacts",
    "local_area_boundary_geojson": "local_area_boundary_geojson",
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


def test_default_db_path_matches_datapaths():
    """Guard against sica_core.config.DEFAULT_DB_PATH and DataPaths drifting apart."""
    assert Path(DEFAULT_DB_PATH) == DataPaths("data").db


def test_default_artifacts_dir_matches_datapaths():
    """Guard against sica_core.config.DEFAULT_ARTIFACTS_DIR and DataPaths drifting apart."""
    assert Path(DEFAULT_ARTIFACTS_DIR) == DataPaths("data").artifacts


def test_fetch_coops_default_output_matches_datapaths():
    """Guard against scripts/fetch_coops.py's DEFAULT_OUT and DataPaths drifting apart."""
    fetch_coops_path = REPO_ROOT / "scripts" / "fetch_coops.py"
    tree = ast.parse(fetch_coops_path.read_text())

    # Extract DEFAULT_OUT from the module-level assignments
    default_out = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DEFAULT_OUT":
                    if isinstance(node.value, ast.Constant):
                        default_out = node.value.value
                    break

    assert default_out is not None, "Could not find DEFAULT_OUT in fetch_coops.py"
    assert default_out == str(DataPaths("data").coops)
