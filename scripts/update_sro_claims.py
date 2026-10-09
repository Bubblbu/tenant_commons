#!/usr/bin/env python3
"""Import the `behind:` pairs in src/tc_core/sro_names.txt as ownership
claims: each company and the person the City's SRO inventory names with it
becomes a confirmed common_owner claim, source_type city_record.

Like scripts/import_lotr_claims.py, this touches ownership_claims only and
does not call init_db(). Idempotent: claims are upserted by a stable
claim_key, so re-run it after every edit to sro_names.txt, then re-export
(scripts/rebuild_data.py --skip-ingest).

Usage: uv run python scripts/update_sro_claims.py [--config config.toml]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tc_core.config import load_ingest_config  # noqa: E402
from tc_core.db import add_missing_columns, get_connection  # noqa: E402
from tc_core.ingest import run_source  # noqa: E402
from tc_core.ingest.sro_claims import import_sro_name_claims  # noqa: E402
from tc_core.ingest.tracking import new_run_id  # noqa: E402
from tc_core.sro_names import load_sro_names  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "config.toml"),
        help="TOML/JSON config with source paths (default: config.toml)",
    )
    args = parser.parse_args()
    config = load_ingest_config(args.config)
    conn = get_connection(config.db_path)
    add_missing_columns(conn)
    try:
        count = run_source(
            conn, new_run_id(), "sro_name_claims", import_sro_name_claims, conn, load_sro_names()
        )
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            parser.error(f"{exc} — run `uv run python scripts/rebuild_data.py` once first.")
        raise
    print(f"{count} city_record claim(s) from sro_names.txt -> {config.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
