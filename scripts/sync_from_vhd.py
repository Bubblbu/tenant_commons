#!/usr/bin/env python3
"""Sync source CSVs from the `vhd` (vancouver-housing-data) pipeline's output
directory into this repo's `data/`.

`vhd` (a separate, un-versioned repo — see docs/DATA_SOURCES.md) is the real
origin pipeline for `buildings.csv` and `property_addresses.csv`: City Open
Data + FOI releases + a hand-maintained `landlord_mapping.toml`, assembled by
`vhd`'s own scripts (`download_data.py`, `merge_foi_releases.py`,
`build_properties.py`, `build_buildings.py`).

This is a deliberate copy step, not a live path reference, for two reasons:

1. `vhd`'s output directory isn't version-controlled — copying into this
   repo's git-tracked `data/` is what gives every ingested vintage a real
   history (`git diff`/`git log` on the CSV), the same way `ownership_claims.csv`
   already works.
2. It can be mid-regeneration at any moment (no atomicity guarantee) — a
   live reference risks reading a half-written file.

Usage:
    uv run python scripts/sync_from_vhd.py --vhd-dir ~/Projects/VTU/vancouver-housing-data-dir
    uv run python scripts/sync_from_vhd.py  # uses $VHD_DATA_DIR

After running, `git diff data/` to review what changed before committing —
same as any other source refresh.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (path relative to vhd dir, path relative to this repo)
MANIFEST = [
    ("processed/buildings.csv", "data/buildings.csv"),
    ("raw/property-addresses.csv", "data/property_addresses.csv"),
    ("raw/local-area-boundary.csv", "data/local-area-boundary.csv"),
]


def _row_count(path: Path) -> int | None:
    if not path.exists():
        return None
    with path.open("rb") as f:
        return sum(1 for _ in f) - 1  # minus header


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vhd-dir",
        default=os.environ.get("VHD_DATA_DIR"),
        help="Path to vhd's output directory (raw/interim/processed/). "
        "Defaults to $VHD_DATA_DIR.",
    )
    args = parser.parse_args()

    if not args.vhd_dir:
        parser.error(
            "--vhd-dir not given and $VHD_DATA_DIR not set. This path is "
            "machine-specific (not committed), per CLAUDE.md's config-not-"
            "hardcoded principle."
        )

    vhd_dir = Path(args.vhd_dir).expanduser()
    if not vhd_dir.is_dir():
        print(f"error: {vhd_dir} is not a directory", file=sys.stderr)
        return 1

    for src_rel, dst_rel in MANIFEST:
        src = vhd_dir / src_rel
        dst = REPO_ROOT / dst_rel
        if not src.exists():
            print(f"skip  {src_rel}: not found in vhd dir")
            continue

        before = _row_count(dst)
        shutil.copyfile(src, dst)
        after = _row_count(dst)

        if before is None:
            print(f"copy  {dst_rel}: new file, {after} rows")
        elif before == after:
            print(f"copy  {dst_rel}: {after} rows (unchanged count, content may still differ)")
        else:
            sign = "+" if after > before else ""
            print(f"copy  {dst_rel}: {before} -> {after} rows ({sign}{after - before})")

    print("\nDone. Review with `git diff data/` before committing, then run "
          "`uv run python scripts/rebuild_map.py` to re-ingest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
