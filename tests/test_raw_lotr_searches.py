"""The LOTR search log (data/raw/samwise/searches/*.csv) records searches,
including those with no filing, so "searched, nothing filed" can be told
apart from "never searched"."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tc_core.db import get_connection, init_db
from tc_core.ingest.raw_lotr_searches import ingest_raw_lotr_searches


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def _log(tmp_path, name, body):
    (tmp_path / name).write_text("pid,searched_on,result,note\n" + body)


def test_logs_from_every_file_are_unioned_and_pids_dashed(tmp_path):
    _log(tmp_path, "manual.csv", "014-344-190,2026-09-30,no_filing,Gainsborough\n")
    _log(tmp_path, "samwise-searches.csv", "004801661,2026-10-02,filed,\n")
    conn = _conn()
    assert ingest_raw_lotr_searches(conn, str(tmp_path)) == 2
    rows = conn.execute(
        "SELECT pid, searched_on, result, note, source_path FROM raw_lotr_searches ORDER BY pid"
    ).fetchall()
    assert rows == [
        ("004-801-661", "2026-10-02", "filed", None, "samwise-searches.csv"),
        ("014-344-190", "2026-09-30", "no_filing", "Gainsborough", "manual.csv"),
    ]


def test_reimport_replaces_and_survives_a_rebuild(tmp_path):
    _log(tmp_path, "manual.csv", "014-344-190,2026-09-30,no_filing,\n")
    conn = _conn()
    ingest_raw_lotr_searches(conn, str(tmp_path))
    ingest_raw_lotr_searches(conn, str(tmp_path))
    init_db(conn)
    assert conn.execute("SELECT count(*) FROM raw_lotr_searches").fetchone()[0] == 1


@pytest.mark.parametrize("row", [
    "14-344-190,2026-09-30,no_filing,",     # short PID
    "014-344-190,30/09/2026,no_filing,",    # not ISO
    "014-344-190,2026-09-30,none,",         # unknown result
])
def test_malformed_rows_fail_the_import(tmp_path, row):
    _log(tmp_path, "manual.csv", row + "\n")
    with pytest.raises(RuntimeError):
        ingest_raw_lotr_searches(_conn(), str(tmp_path))


def _export_log(tmp_path, body):
    (tmp_path / "samwise-searches-2026-10-06.csv").write_text(
        "pid,searched_on,result,note,result_count,searched_at\n" + body
    )


def test_samwise_export_columns_are_kept(tmp_path):
    _log(tmp_path, "manual.csv", "014-344-190,2026-09-30,no_filing,\n")
    _export_log(tmp_path, "007-043-899,2026-10-06,no_filing,,0,2026-10-06 18:23\n")
    conn = _conn()
    ingest_raw_lotr_searches(conn, str(tmp_path))
    rows = conn.execute(
        "SELECT pid, result_count, searched_at FROM raw_lotr_searches ORDER BY pid"
    ).fetchall()
    assert rows == [("007-043-899", 0, "2026-10-06 18:23"), ("014-344-190", None, None)]


@pytest.mark.parametrize("row", [
    "007-043-899,2026-10-06,no_filing,,2,2026-10-06 18:23",   # count says filed
    "007-043-899,2026-10-06,filed,,0,2026-10-06 18:23",       # count says no filing
    "007-043-899,2026-10-06,filed,,many,2026-10-06 18:23",    # not a count
    "007-043-899,2026-10-06,filed,,1,06/10/2026 18:23",       # not ISO
])
def test_inconsistent_export_rows_fail_the_import(tmp_path, row):
    _export_log(tmp_path, row + "\n")
    with pytest.raises(RuntimeError):
        ingest_raw_lotr_searches(_conn(), str(tmp_path))
