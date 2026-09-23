#!/usr/bin/env python3
"""Fetch the Vancouver Open Data files into data/raw/cov_open_data/.

Usage:
    uv run python scripts/fetch_cov_open_data.py
    uv run python scripts/fetch_cov_open_data.py --only block-numbers block-outlines
    uv run python scripts/fetch_cov_open_data.py --tax-report-year 2027

The property tax report is large (~200 MB as GeoJSON) and business licences
~140 MB; a full fetch takes several minutes. Afterwards, update the fetch
dates in data/raw/cov_open_data/MANIFEST.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tc_core.fetch.cov_open_data import DEFAULT_TAX_REPORT_YEAR, fetch_all  # noqa: E402
from tc_core.paths import DataPaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument("--only", nargs="+", help="dataset ids to fetch (default: all)")
    parser.add_argument("--tax-report-year", type=int, default=DEFAULT_TAX_REPORT_YEAR)
    args = parser.parse_args()

    paths = DataPaths(args.data_dir)
    fetch_all(paths.cov_open_data, args.tax_report_year, args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
