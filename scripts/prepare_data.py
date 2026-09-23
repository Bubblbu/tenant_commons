#!/usr/bin/env python3
"""Build the derived tables from raw/ and curated/.

Stages, in dependency order:
  foi         raw/cov_foi 2023 + 2024 extracts  -> derived/interim/all_rentals.csv
  properties  raw/cov_open_data + raw/vanmaps   -> derived/interim/properties.csv
  buildings   the above + curated/              -> derived/buildings.csv, ct_properties.csv

Usage: uv run python scripts/prepare_data.py [--data-dir data] [--stage all]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tc_core.paths import DataPaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument(
        "--stage", choices=["foi", "properties", "buildings", "all"], default="all"
    )
    args = parser.parse_args()
    paths = DataPaths(args.data_dir)
    stage = args.stage

    if stage in ("foi", "all"):
        from tc_core.prepare.foi import merge_foi_releases

        merge_foi_releases(paths.foi_2023_extract, paths.foi_2024_extract, paths.all_rentals)
    if stage in ("properties", "all"):
        from tc_core.prepare import properties

        properties.run(paths)
    if stage in ("buildings", "all"):
        from tc_core.prepare import buildings

        buildings.run(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
