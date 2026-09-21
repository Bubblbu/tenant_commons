#!/usr/bin/env python3
"""Freeze today's match_overlays() output so the port into sica_core can be
verified against it.

Throwaway — delete once the port has landed (see the plan's Task 5). Keyed on
addr_key, not b_id: synthetic rows get b_id assigned at render time, and the
port changes that assignment.

Usage: uv run python scripts/overlay_fingerprint.py --out <path>
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


def _housing_type(row) -> str:
    if bool(row.get("is_coop")):
        return "coop"
    if bool(row.get("is_sro")):
        return "sro"
    return "none"


def fingerprint_overlays(pts_df: pd.DataFrame) -> dict:
    """Stable summary of overlay matching: counts by type plus a sorted key set."""
    types = [_housing_type(r) for _, r in pts_df.iterrows()]
    counts: dict[str, int] = {"coop": 0, "sro": 0, "none": 0}
    for t in types:
        counts[t] += 1
    counts["total"] = len(types)

    keys = [
        [str(k), t, str(la) if pd.notna(la) else ""]
        for k, t, la in zip(pts_df["addr_key"], types, pts_df["local_area"])
    ]
    keys.sort()
    return {"counts": counts, "keys": keys}


def main() -> int:
    from sica_core.config import load_ingest_config
    from sica_core.db import get_connection
    from sica_core.export import reconstruct_points
    from sica_mapping.data import (
        local_area_boundaries_feature_collection,
        match_overlays,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(REPO_ROOT / "config.toml"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = load_ingest_config(args.config)
    # IngestConfig has no local_area_boundary field (the boundary CSV is only
    # used by sica_mapping today), so read that one path straight from the
    # TOML rather than widening IngestConfig for a throwaway script.
    boundary_csv = tomllib.loads(
        Path(args.config).read_text(encoding="utf-8")
    )["paths"]["local_area_boundary"]

    conn = get_connection(config.db_path)
    pts_df = reconstruct_points(
        conn, pd.Timestamp.now(tz="UTC"), config.pid_address_map
    )
    result = match_overlays(
        pts_df,
        coops_path=config.coops,
        sro_path=config.sro_housing,
        rezoning_path=config.rezoning_applications,
        local_area_boundary_fc=local_area_boundaries_feature_collection(
            boundary_csv
        ),
        buildings_path=config.buildings,
    )
    fp = fingerprint_overlays(result.pts_df)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fp, indent=2), encoding="utf-8")
    print(f"wrote {out}: {fp['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
