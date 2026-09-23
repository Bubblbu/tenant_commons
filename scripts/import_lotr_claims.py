#!/usr/bin/env python3
"""Import a Samwise (BC Land Owner Transparency Registry) export into
tc_core: raw rows into raw_lotr_ownership, then derived common_owner
claims into ownership_claims.

Decoupled from the main tc_core rebuild cadence — like
scripts/update_claims.py, this deliberately does NOT call init_db(), since
that drops and recreates every REBUILDABLE table (buildings, addresses,
blocks, membership); doing that here would silently wipe them for a script
whose whole point is touching LOTR data only.

Both steps are idempotent: ingest_raw_lotr() replaces raw_lotr_ownership's
contents wholesale on each run, and derive_lotr_ownership_claims() upserts
by a deterministic claim_key, so re-running against a refreshed Samwise
export is always safe.

See src/tc_core/ingest/lotr_claims.py for the entity-pair extraction
logic and src/tc_core/schema.sql for why raw_lotr_ownership is PERSISTENT
rather than REBUILDABLE.

Usage: uv run python scripts/import_lotr_claims.py [--config config.toml] [--lotr-csv path]
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
from tc_core.ingest.lotr_claims import derive_lotr_ownership_claims  # noqa: E402
from tc_core.ingest.raw_lotr import ingest_raw_lotr  # noqa: E402
from tc_core.ingest.tracking import new_run_id  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "config.toml"),
        help="TOML/JSON config with source paths (default: config.toml)",
    )
    parser.add_argument(
        "--lotr-csv",
        default=None,
        help="Override the Samwise LOTR export path from config",
    )
    args = parser.parse_args()

    config = load_ingest_config(args.config)
    lotr_path = args.lotr_csv or config.lotr_ownership
    if not lotr_path:
        parser.error(
            "no lotr_ownership path configured — set `lotr_ownership` under "
            "[paths] in config.toml, or pass --lotr-csv explicitly"
        )

    conn = get_connection(config.db_path)
    run_id = new_run_id()
    try:
        raw_count = run_source(conn, run_id, "raw_lotr_ownership", ingest_raw_lotr, conn, lotr_path)
        claim_count = run_source(
            conn, run_id, "lotr_claims", derive_lotr_ownership_claims, conn
        )
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            parser.error(
                f"{exc} — run `uv run python scripts/rebuild_data.py` (or "
                "`python -m tc_core.ingest --config ...`) at least once first "
                "to initialize the database."
            )
        raise

    print(
        f"{raw_count} raw LOTR row(s) from {lotr_path}, "
        f"{claim_count} common_owner claim(s) derived -> {config.db_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
