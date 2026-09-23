#!/usr/bin/env python3
"""Bulk-import ownership_claims from a CSV, without re-running the full
tc_core pipeline (buildings/addresses/blocks/membership stay untouched).

Upserts by claim_key — safe to re-run repeatedly as the claims CSV evolves
(existing claim_key -> updates that row in place; new claim_key -> inserts).
See CLAUDE.md Section 3 ("Claims ingestion & entity resolution") and
src/tc_core/claims.py for the underlying semantics.

Assumes the database has already been initialized at least once (via
scripts/rebuild_data.py or `python -m tc_core.ingest`) — this script
deliberately does NOT call init_db(), since that drops and recreates every
REBUILDABLE table (buildings, addresses, blocks, membership); doing that
here would silently wipe them for a script whose whole point is touching
claims only.

Lives at the top level (like fetch_coops.py, rebuild_data.py), matching this
repo's existing convention for standalone entry points.

Usage: uv run python scripts/update_claims.py [--config config.toml] [--claims-csv path]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tc_core.config import load_ingest_config  # noqa: E402
from tc_core.db import get_connection  # noqa: E402
from tc_core.ingest import run_source  # noqa: E402
from tc_core.ingest.ownership_claims import ingest_ownership_claims  # noqa: E402
from tc_core.ingest.tracking import new_run_id  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "config.toml"),
        help="TOML/JSON config with source paths (default: config.toml)",
    )
    parser.add_argument(
        "--claims-csv",
        default=None,
        help="Override the ownership_claims CSV path from config",
    )
    args = parser.parse_args()

    config = load_ingest_config(args.config)
    claims_path = args.claims_csv or config.ownership_claims
    if not claims_path:
        parser.error(
            "no ownership_claims path configured — set `ownership_claims` under "
            "[paths] in config.toml, or pass --claims-csv explicitly"
        )

    conn = get_connection(config.db_path)
    run_id = new_run_id()
    try:
        n = run_source(conn, run_id, "ownership_claims", ingest_ownership_claims, conn, claims_path)
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            parser.error(
                f"{exc} — run `uv run python scripts/rebuild_data.py` (or "
                "`python -m tc_core.ingest --config ...`) at least once first "
                "to initialize the database."
            )
        raise

    print(f"{n} claim(s) processed from {claims_path} -> {config.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
