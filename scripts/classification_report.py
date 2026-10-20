#!/usr/bin/env python3
"""Building classification: research CSVs and an eyeball report (spec 2026-10-20).

Reads the exported building_records.json, so it sees exactly what the map
publishes. Writes data/derived/classification/{buildings,entities}.csv and
prints counts per axis, the most common name-rule kinds to spot-check, every
mixed building, and owners whose kind differs from the licence holder's.
An axis that is null in the export (nothing known) shows as empty.

Usage: uv run python scripts/classification_report.py [--config config.toml]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tc_core.config import load_ingest_config  # noqa: E402


def _row(r: dict) -> dict:
    c = r["classification"]
    owner, market, op = c["owner"] or {}, c["market"] or {}, c["operator"] or {}
    return {
        "b_id": r["id"], "address": r["address"], "local_area": r["local_area"], "units": r["units"],
        "owner_type": owner.get("value"), "owner_legal_forms": ";".join(owner.get("legal_forms", [])),
        "owner_parts": ";".join(owner.get("parts", [])), "owner_reason": owner.get("reason"),
        "owner_basis": ";".join(owner.get("basis", [])), "owner_inferred": owner.get("inferred"),
        "market": market.get("value"), "market_basis": ";".join(market.get("basis", [])),
        "market_inferred": market.get("inferred"), "operator_type": op.get("value"),
        "scale": c["scale"], "network_id": r["network_id"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(REPO_ROOT / "config.toml"))
    args = parser.parse_args()
    config = load_ingest_config(args.config)
    records = json.loads((Path(config.artifacts) / "building_records.json").read_text())["records"]

    entities: Counter = Counter()
    for r in records.values():
        for p in r["parties"]:
            entities[(p["name"], p["entity_key"], p["role"], p["kind"], p["institutional"])] += 1

    out = Path(config.artifacts).parent / "classification"
    out.mkdir(parents=True, exist_ok=True)
    buildings = pl.DataFrame([_row(r) for r in records.values()], infer_schema_length=None)
    buildings.write_csv(out / "buildings.csv")
    pl.DataFrame(
        [{"name": n, "entity_key": k, "role": role, "kind": kind, "institutional": inst, "buildings": count}
         for (n, k, role, kind, inst), count in entities.items()],
        infer_schema_length=None,
    ).sort("buildings", descending=True).write_csv(out / "entities.csv")

    with pl.Config(tbl_rows=30):
        for axis in ("owner_type", "owner_inferred", "owner_legal_forms", "market", "market_inferred",
                     "operator_type", "scale"):
            print(f"\n{axis}:")
            print(buildings.group_by(axis).agg(buildings=pl.len(), units=pl.col("units").sum())
                  .sort("buildings", descending=True))
        print("\nMixed buildings:")
        print(buildings.filter(pl.col("owner_type") == "mixed").select("address", "owner_parts", "owner_reason"))
    print("\nMost common owner kinds (spot-check these):")
    owners = [(n, kind, count) for (n, _, role, kind, _), count in entities.most_common() if role == "owner"]
    for name, kind, count in owners[:50]:
        print(f"  {kind or '-':17} {count:4}  {name}")
    print("\nOwner vs licence holder kind disagreements:")
    for r in records.values():
        kinds = {p["kind"] for p in r["parties"] if p["role"] == "owner" and p["kind"]}
        lic = next((p for p in r["parties"] if p["role"] == "licensee" and p["same_as"] is None), None)
        if kinds and lic and lic["kind"] and lic["kind"] not in kinds:
            print(f"  {r['address']}: owner {sorted(kinds)} vs licensee {lic['name']} ({lic['kind']})")
    print(f"\nWrote {out / 'buildings.csv'} and {out / 'entities.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
