"""Ingest the LOTR search log into raw_lotr_searches.

raw_lotr_ownership only holds PIDs whose search returned a filing, so on
its own a PID with no rows could mean "never searched" or "searched, no
filing". The search log records the searches themselves, so the two can be
told apart.

Every *.csv under the configured directory (data/raw/samwise/searches/)
is read and unioned: a hand-kept manual.csv and Samwise's own search
exports (samwise-searches-<date>.csv). Columns:

    pid           ddd-ddd-ddd
    searched_on   YYYY-MM-DD
    result        no_filing | filed
    note          optional free text
    result_count  optional (Samwise exports): filings found, 0 iff no_filing
    searched_at   optional (Samwise exports): YYYY-MM-DD HH:MM

Malformed rows fail the import rather than being skipped. PERSISTENT, like
raw_lotr_ownership, and imported alongside it by
scripts/import_lotr_claims.py: each run replaces the table's contents.
export.py publishes only the date a building's PIDs were searched with no
filing (metrics/registry_owners.py::build_registry_searches), never notes.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

COLUMNS = ["pid", "searched_on", "result", "note"]
RESULTS = {"no_filing", "filed"}
_PID_RE = re.compile(r"^\d{3}-\d{3}-\d{3}$")


def _pid(value: str) -> str:
    """Accepts dashed or bare 9-digit PIDs; stores the dashed form LOTR uses."""
    digits = re.sub(r"\D", "", value)
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}" if len(digits) == 9 else value


def _result_count(path: Path, line: int, value: str | None, result: str) -> int | None:
    """The export's filing count, checked against its result; None if the file has none."""
    value = (value or "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise RuntimeError(f"{path}:{line}: bad result_count {value!r}")
    count = int(value)
    if (count == 0) != (result == "no_filing"):
        raise RuntimeError(f"{path}:{line}: result_count {count} contradicts result {result!r}")
    return count


def load_search_rows(searches_dir: str) -> list[dict]:
    rows = []
    for path in sorted(Path(searches_dir).glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            missing = set(COLUMNS[:3]) - set(reader.fieldnames or [])
            if missing:
                raise RuntimeError(f"{path}: missing column(s) {sorted(missing)}")
            for line, rec in enumerate(reader, start=2):
                pid = _pid((rec.get("pid") or "").strip())
                searched_on = (rec.get("searched_on") or "").strip()
                result = (rec.get("result") or "").strip()
                if not _PID_RE.match(pid):
                    raise RuntimeError(f"{path}:{line}: bad pid {rec.get('pid')!r}")
                try:
                    date.fromisoformat(searched_on)
                except ValueError:
                    raise RuntimeError(f"{path}:{line}: bad searched_on {searched_on!r}") from None
                if result not in RESULTS:
                    raise RuntimeError(f"{path}:{line}: result must be one of {sorted(RESULTS)}, got {result!r}")
                result_count = _result_count(path, line, rec.get("result_count"), result)
                searched_at = (rec.get("searched_at") or "").strip() or None
                if searched_at is not None:
                    try:
                        datetime.fromisoformat(searched_at)
                    except ValueError:
                        raise RuntimeError(f"{path}:{line}: bad searched_at {searched_at!r}") from None
                rows.append({
                    "pid": pid,
                    "searched_on": searched_on,
                    "result": result,
                    "note": (rec.get("note") or "").strip() or None,
                    "result_count": result_count,
                    "searched_at": searched_at,
                    "source_path": path.name,
                })
    return rows


def ingest_raw_lotr_searches(conn: sqlite3.Connection, searches_dir: str) -> int:
    rows = load_search_rows(searches_dir)
    ingested_at = datetime.now(UTC).isoformat()
    with conn:
        conn.execute("DELETE FROM raw_lotr_searches")
        conn.executemany(
            "INSERT INTO raw_lotr_searches (pid, searched_on, result, note, result_count, "
            "searched_at, source_path, ingested_at) VALUES (:pid, :searched_on, :result, :note, "
            ":result_count, :searched_at, :source_path, :ingested_at)",
            [{**r, "ingested_at": ingested_at} for r in rows],
        )
    return len(rows)
