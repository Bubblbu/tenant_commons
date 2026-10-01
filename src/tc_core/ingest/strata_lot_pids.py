"""Ingest the hand-kept strata lot PID -> strata plan map into strata_lot_pids.

The City's address points and building records identify a strata building
by its plan number (raw_buildings.pid "VAS684") rather than a PID, but LOTR
files against each strata lot's own PID. This file says which plan a
searched lot belongs to, so its filing reaches every building carrying that
plan (metrics/portfolios.py::_building_pids). One searched lot per building
is enough for a rental strata, where one company owns every lot and holds the
building's rental licence; a strata whose lots are sold to different owners
would take one lot's owner for the whole building, so don't list it. Columns:

    pid          lot PID, dashed or bare 9 digits
    strata_plan  e.g. VAS684 (stored upper-case, no spaces)
    note         optional free text

Malformed rows fail the ingest rather than being skipped.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

_PLAN_RE = re.compile(r"^[A-Z]{2,4}\d+$")


def load_strata_lot_rows(path: str) -> list[dict]:
    rows = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {"pid", "strata_plan"} - set(reader.fieldnames or [])
        if missing:
            raise RuntimeError(f"{path}: missing column(s) {sorted(missing)}")
        for line, rec in enumerate(reader, start=2):
            digits = re.sub(r"\D", "", rec.get("pid") or "")
            plan = re.sub(r"\s", "", rec.get("strata_plan") or "").upper()
            if len(digits) != 9:
                raise RuntimeError(f"{path}:{line}: bad pid {rec.get('pid')!r}")
            if not _PLAN_RE.match(plan):
                raise RuntimeError(f"{path}:{line}: bad strata_plan {rec.get('strata_plan')!r}")
            rows.append({
                "pid": f"{digits[:3]}-{digits[3:6]}-{digits[6:]}",
                "strata_plan": plan,
                "note": (rec.get("note") or "").strip() or None,
            })
    return rows


def ingest_strata_lot_pids(conn: sqlite3.Connection, path: str) -> int:
    rows = load_strata_lot_rows(path)
    with conn:
        conn.execute("DELETE FROM strata_lot_pids")
        conn.executemany(
            "INSERT INTO strata_lot_pids (pid, strata_plan, note) VALUES (:pid, :strata_plan, :note)",
            rows,
        )
    return len(rows)
