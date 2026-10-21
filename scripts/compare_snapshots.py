#!/usr/bin/env python3
"""Snapshot the pipeline's outputs and compare two snapshots, to check that a
refactor (e.g. a pandas -> polars port) leaves every output unchanged.

A snapshot is a copy of data/curated/ and data/derived/. Files are compared
byte for byte, except the SQLite db, which is compared table by table,
ignoring run timestamps (*_at columns) and the append-only ingest_runs log.

Snapshots hold the database, claim notes and reporters included, so they
must live outside the repo; `snapshot` refuses a destination inside it.

Usage:
  uv run python scripts/compare_snapshots.py snapshot DEST
  uv run python scripts/compare_snapshots.py compare SNAPSHOT_A SNAPSHOT_B

Typical loop: rebuild (prepare_data.py, rebuild_data.py), snapshot as the
baseline, make the change, rebuild, snapshot again, compare.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
PARTS = ("curated", "derived")


def snapshot(dest: Path) -> None:
    dest = dest.resolve()
    if dest.is_relative_to(REPO_ROOT):
        sys.exit(f"refusing to snapshot inside the repo (it holds claim notes): {dest}")
    if dest.exists():
        sys.exit(f"already exists: {dest}")
    for part in PARTS:
        shutil.copytree(DATA / part, dest / part)
    print(f"snapshot -> {dest}")


def _table_rows(db: Path) -> dict[str, list[str]]:
    conn = sqlite3.connect(db)
    out = {}
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        if table == "ingest_runs":
            continue
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        keep = ", ".join(c for c in cols if not c.endswith("_at"))
        out[table] = sorted(map(repr, conn.execute(f"SELECT {keep} FROM {table}")))
    conn.close()
    return out


def compare(a: Path, b: Path) -> list[str]:
    for snap in (a, b):
        if not (snap / "derived").is_dir():
            sys.exit(f"not a snapshot (no derived/): {snap}")
    files_a = {p.relative_to(a) for p in a.rglob("*") if p.is_file()}
    files_b = {p.relative_to(b) for p in b.rglob("*") if p.is_file()}
    problems = [f"only in A: {rel}" for rel in sorted(files_a - files_b)]
    problems += [f"only in B: {rel}" for rel in sorted(files_b - files_a)]
    for rel in sorted(files_a & files_b):
        if rel.suffix == ".db":
            rows_a, rows_b = _table_rows(a / rel), _table_rows(b / rel)
            problems += [
                f"db table differs: {rel}:{table}"
                for table in sorted(rows_a.keys() | rows_b.keys())
                if rows_a.get(table) != rows_b.get(table)
            ]
        elif not filecmp.cmp(a / rel, b / rel, shallow=False):
            problems.append(f"differs: {rel}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot").add_argument("dest", type=Path)
    cmp = sub.add_parser("compare")
    cmp.add_argument("a", type=Path)
    cmp.add_argument("b", type=Path)
    args = parser.parse_args()

    if args.command == "snapshot":
        snapshot(args.dest)
        return 0
    problems = compare(args.a, args.b)
    print("\n".join(problems) or "IDENTICAL (ignoring run timestamps)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
