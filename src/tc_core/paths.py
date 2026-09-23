"""The data/ layout, defined once.

Stages: raw/ (as received, never hand-edited) + curated/ (hand-authored)
-> derived/ (regenerable) -> exports/ (what leaves the pipeline).
config.toml's [paths] is read by the ingest and by scripts/rebuild_map.py; a test
(tests/test_data_layout.py) keeps it in agreement with this class.
"""

from __future__ import annotations

from pathlib import Path


class DataPaths:
    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)
        self.raw = self.root / "raw"
        self.curated = self.root / "curated"
        self.derived = self.root / "derived"
        self.interim = self.derived / "interim"
        self.exports = self.root / "exports"

        # raw/ sources
        self.cov_open_data = self.raw / "cov_open_data"
        self.cov_foi = self.raw / "cov_foi"
        self.vanmaps = self.raw / "vanmaps"
        self.chf_bc = self.raw / "chf_bc"
        self.nationbuilder = self.raw / "nationbuilder"
        self.samwise = self.raw / "samwise"

        self.property_addresses_csv = self.cov("property-addresses", "csv")
        self.local_area_boundary_csv = self.cov("local-area-boundary", "csv")
        self.block_outlines_csv = self.cov("block-outlines", "csv")
        self.block_numbers_csv = self.cov("block-numbers", "csv")
        self.local_area_boundary_geojson = self.cov("local-area-boundary", "geojson")

        self.foi_2023_extract = self.cov_foi / "all_rentals.2023-186.csv"
        self.foi_2024_extract = self.cov_foi / "2024-698_extracted_data.csv"
        self.sro_housing = self.cov_foi / "sra_housing_combined.csv"
        self.rezoning_applications = self.cov_foi / "rezoning_applications.csv"

        self.vanmaps_addresses = self.vanmaps / "addresses.geojson"
        self.coops = self.chf_bc / "coops_vancouver.csv"
        self.membership_full = self.nationbuilder / "membership_full.csv"
        self.samwise_export = self.samwise / "samwise-export.csv"

        # curated/
        self.ownership_claims = self.curated / "ownership_claims.csv"
        self.landlord_mapping = self.curated / "landlord_mapping.toml"
        self.chinatown_boundary = self.curated / "chinatown_boundary.geojson"

        # derived/
        self.all_rentals = self.interim / "all_rentals.csv"
        self.properties = self.interim / "properties.csv"
        self.buildings = self.derived / "buildings.csv"
        self.ct_properties = self.derived / "ct_properties.csv"
        self.pid_address_map = self.derived / "pid_address_map.csv"
        self.db = self.derived / "tc_core.db"
        self.artifacts = self.derived / "artifacts"

    def cov(self, dataset: str, fmt: str) -> Path:
        """A file fetched from Vancouver Open Data, e.g. cov('block-numbers', 'csv')."""
        return self.cov_open_data / f"{dataset}.{fmt}"
