# Overlay Port and Data Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move SRO/co-op/rezoning overlay matching out of the map renderer into `sica_core`'s ingest, and make `sica_core.export` the sole producer of a complete frontend artifact set.

**Architecture:** `match_overlays()` currently runs at render time against CSVs and mutates the points frame. It moves to an ingest-time step reading `raw_sro`/`raw_coops`/`raw_rezoning` from SQLite. Records that match a building set flags on that building; records that match nothing go to a new `overlay_housing` companion table rather than being merged into `buildings`. The export then unions the two and emits `blocks.geojson` plus `lat`/`lon` in marker metadata. The map still renders through Folium at the end of this plan — Folium removal is the follow-on plan.

**Tech Stack:** Python 3.12, pandas, shapely, SQLite (stdlib `sqlite3`), pytest, `uv` for running.

**Spec:** [`docs/superpowers/specs/2026-09-19-renderer-rewrite-design.md`](../specs/2026-09-19-renderer-rewrite-design.md) — implements §4, §5, and §9 steps 1–3.

## Global Constraints

- **Git.** The user has a standing rule to ask before any git action. For this run they have authorized exactly one thing: committing each task on the branch `overlay-port-data-contract`. Never push, merge, rebase, amend, tag, switch branches, or touch `main`. Stage explicit paths only — never `git add -A` / `git add .` (uncommitted design docs live in the working tree).
- **Never add Claude attribution** to commit messages or PR descriptions.
- `sica_core` must not import from `sica_mapping`. Scripts at the top level may import both.
- Ingest raises on any unmapped source column — add it to the relevant `RAW_*_COLUMNS` list and `schema.sql` rather than dropping it silently.
- `ownership_claims`, `ingest_runs` and `raw_lotr_ownership` are PERSISTENT (`CREATE TABLE IF NOT EXISTS`, never dropped). Everything else in `schema.sql` is REBUILDABLE.
- Run everything through `uv run`. Tests: `uv run pytest -q`. The suite is 26 tests and green — it must stay green at every commit.
- Existing test conventions: no `conftest.py`, no fixtures module, tests import `sica_core.*` directly and use pytest's `tmp_path`.
- The map must still render at the end of this plan: `uv run python scripts/rebuild_map.py` produces `www/index.html`.
- Test fixtures inserting into `buildings` must supply `created_at` and `updated_at`; into `blocks`, `ingested_at`; into `ownership_claims`, `source_type`, `created_at` and `updated_at` — all are `NOT NULL` with no default.
- "Expected: N passed" counts are advisory. The binding requirement is that the whole suite is green, with count = previous + tests added − tests removed.

---

### Task 1: Freeze the overlay fingerprint

Captures today's `match_overlays()` behaviour before anything moves, so the port can be verified. Throwaway — deleted in Task 5.

Keyed on `addr_key`, **not** `b_id`: synthetic rows get `b_id = max + 1` assigned at render time by `_append_extra_housing`, so moving them changes every such id and a `b_id`-keyed fingerprint would diff on all 153 rows regardless of whether matching changed.

**Files:**
- Create: `scripts/overlay_fingerprint.py`
- Create: `tests/fixtures/overlay_fingerprint_baseline.json` (generated, committed)
- Test: `tests/test_overlay_fingerprint.py`

**Interfaces:**
- Produces: `fingerprint_overlays(pts_df: pd.DataFrame) -> dict` — returns `{"counts": {...}, "keys": [[addr_key, housing_type, local_area], ...]}` with `keys` sorted. Used by Task 5 to verify the port.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_overlay_fingerprint.py
import pandas as pd

from overlay_fingerprint import fingerprint_overlays


def _frame():
    return pd.DataFrame(
        {
            "addr_key": ["100 main st", "200 oak st", "300 elm st"],
            "local_area": ["Downtown", "Kitsilano", "Downtown"],
            "is_coop": [True, False, False],
            "is_sro": [False, True, False],
        }
    )


def test_counts_by_type():
    fp = fingerprint_overlays(_frame())
    assert fp["counts"] == {"coop": 1, "sro": 1, "none": 1, "total": 3}


def test_keys_are_sorted_and_keyed_on_addr_key():
    fp = fingerprint_overlays(_frame())
    assert fp["keys"] == [
        ["100 main st", "coop", "Downtown"],
        ["200 oak st", "sro", "Kitsilano"],
        ["300 elm st", "none", "Downtown"],
    ]


def test_is_deterministic_regardless_of_row_order():
    a = fingerprint_overlays(_frame())
    b = fingerprint_overlays(_frame().iloc[::-1].reset_index(drop=True))
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_overlay_fingerprint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'overlay_fingerprint'`

- [ ] **Step 3: Write the script**

```python
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
```

- [ ] **Step 4: Make the script importable by the test**

Add to `pyproject.toml` so `scripts/` is on the path for pytest:

```toml
[tool.pytest.ini_options]
pythonpath = ["src", "scripts"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_overlay_fingerprint.py -v`
Expected: 3 passed

- [ ] **Step 6: Generate the baseline against real data**

Run: `uv run python scripts/overlay_fingerprint.py --out tests/fixtures/overlay_fingerprint_baseline.json`
Expected: prints counts with `total` = 5281, `coop` = 36 + matched co-ops, `sro` = 117 + matched SROs.

Record the printed counts in the commit message — Task 5 compares against them.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: 29 passed

- [ ] **Step 8: Commit** *(ask first)*

```bash
git add scripts/overlay_fingerprint.py tests/test_overlay_fingerprint.py \
        tests/fixtures/overlay_fingerprint_baseline.json pyproject.toml
git commit -m "Freeze overlay-matching fingerprint before porting into sica_core"
```

---

### Task 2: Add the `overlay_housing` table

Per spec §5: unmatched SRO/co-op records get a companion table rather than being appended to `buildings`, so `buildings` keeps meaning "a building we have property data for" and the unmatched count stays visible as a data-quality metric.

**Files:**
- Modify: `src/sica_core/schema.sql` (REBUILDABLE section, after `raw_rezoning`)
- Test: `tests/test_overlay_housing_schema.py`

**Interfaces:**
- Produces: table `overlay_housing(overlay_id, addr_key, address, housing_name, local_area, lat, lon, is_coop, is_sro, coop_status, coop_ownership_model, coop_url, sro_owner, sro_operator, sro_operator_group, sro_ownership_group, sro_occupancy_status, sro_registered_rooms, source_row_ids, ingested_at)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_overlay_housing_schema.py
import sqlite3

from sica_core.db import init_db


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info('{table}')")}


def test_overlay_housing_exists_with_expected_columns():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    cols = _columns(conn, "overlay_housing")
    assert {
        "overlay_id",
        "addr_key",
        "address",
        "housing_name",
        "local_area",
        "lat",
        "lon",
        "is_coop",
        "is_sro",
        "coop_status",
        "sro_owner",
        "source_row_ids",
        "ingested_at",
    } <= cols


def test_overlay_housing_is_rebuildable():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO overlay_housing (addr_key, address, lat, lon, ingested_at) "
        "VALUES ('x', 'x', 1.0, 2.0, 'now')"
    )
    conn.commit()
    init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM overlay_housing").fetchone()[0] == 0


def test_ownership_claims_still_survives_rebuild():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO ownership_claims (claim_key, entity_a, entity_b, relationship, "
        "source_type, created_at, updated_at) "
        "VALUES ('k', 'a', 'b', 'same_entity', 'manual_research', 'now', 'now')"
    )
    conn.commit()
    init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM ownership_claims").fetchone()[0] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_overlay_housing_schema.py -v`
Expected: FAIL — `sqlite3.OperationalError: no such table: overlay_housing`

- [ ] **Step 3: Add the table to schema.sql**

Insert into the REBUILDABLE section, immediately after the `raw_rezoning` table definition:

```sql
-- SRO/co-op source records whose address matched no building (see
-- ingest/overlays.py). Deliberately NOT merged into `buildings`: these are a
-- matching *failure* artifact, not buildings we have property data for.
-- Keeping them separate means COUNT(*) over `buildings` stays correct without
-- remembering to filter, and this table's own row count is a visible
-- data-quality metric — if it grows, address matching regressed.
-- The export unions the two (see export.py) with a real `source` discriminator.
DROP TABLE IF EXISTS overlay_housing;
CREATE TABLE overlay_housing (
    overlay_id INTEGER PRIMARY KEY,
    addr_key TEXT NOT NULL,
    address TEXT,
    housing_name TEXT,
    local_area TEXT,
    lat REAL,
    lon REAL,
    is_coop INTEGER NOT NULL DEFAULT 0,
    is_sro INTEGER NOT NULL DEFAULT 0,
    coop_status TEXT,
    coop_ownership_model TEXT,
    coop_url TEXT,
    sro_owner TEXT,
    sro_operator TEXT,
    sro_operator_group TEXT,
    sro_ownership_group TEXT,
    sro_occupancy_status TEXT,
    sro_registered_rooms TEXT,
    source_row_ids TEXT,   -- lineage hook (CLAUDE.md Q8c): raw_sro/raw_coops ids
    ingested_at TEXT NOT NULL
);
CREATE INDEX idx_overlay_housing_addr_key ON overlay_housing(addr_key);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_overlay_housing_schema.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: 32 passed

- [ ] **Step 6: Commit** *(ask first)*

```bash
git add src/sica_core/schema.sql tests/test_overlay_housing_schema.py
git commit -m "Add overlay_housing table for unmatched SRO/co-op records"
```

---

### Task 3: SQLite-backed loaders for the overlay port

The matching logic stays byte-identical; only its *inputs* change from CSV reads to SQLite reads. This task builds those input functions in isolation so Task 4 is a pure move.

Replaces three CSV readers in `src/sica_mapping/data/overlays.py`:
`_load_optional_csv` (lines 76-83), `_load_secondary_address_index` (85-121), and the `local_area_boundary_fc` argument.

**Files:**
- Create: `src/sica_core/ingest/overlay_sources.py`
- Test: `tests/test_overlay_sources.py`

**Interfaces:**
- Consumes: tables `raw_sro`, `raw_coops`, `raw_rezoning`, `raw_buildings` (Task 2's schema is unchanged by this task).
- Produces:
  - `load_sro_frame(conn) -> pd.DataFrame | None` — columns `raw_sro_id`, `address`, `secondary_address`, `building_name`, `owner`, `operator`, `operator_group`, `ownership_group`, `occupancy_status`, `#_registered_rooms`, `latitude`, `longitude`. `None` when the table is empty. **Column names match what the matcher body reads, not the table's own names:** `raw_sro.registered_rooms` is returned as `#_registered_rooms`, because the ported body reads `row.get("#_registered_rooms")` (the CSV's normalized header) and must stay byte-identical. A mismatch here fails silently — `.get()` returns `None` and the field is just blank.
  - `load_coops_frame(conn) -> pd.DataFrame | None` — columns `title`, `address`, `lat`, `lon`, `status`, `ownership_model`, `website`, `read_more_url`, `raw_coop_id`. `None` when empty.
  - `load_rezoning_frame(conn) -> pd.DataFrame | None` — all `raw_rezoning` columns. `None` when empty.
  - `load_secondary_address_index(conn) -> dict[str, str]` — maps each secondary address's key to its building's primary key. **A faithful port of `overlays.py::_load_secondary_address_index` (lines 85-121):** both keys through `sica_core.normalize.addr_key_from_freeform` (identical to `sica_mapping`'s copy — verified), split on `";"` only, first building to claim a secondary wins, no extra filtering. Plain lowercasing is wrong: `addr_key_from_freeform("102 Main Street")` is `"102 main st"`, so a lowercased key would silently never match.
  - `load_boundary_feature_collection(path) -> dict` — reads `local-area-boundary.geojson` straight off disk.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_overlay_sources.py
import json
import sqlite3

from sica_core.db import init_db
from sica_core.ingest.overlay_sources import (
    load_boundary_feature_collection,
    load_coops_frame,
    load_secondary_address_index,
    load_sro_frame,
)


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def test_returns_none_when_table_empty():
    conn = _conn()
    assert load_sro_frame(conn) is None
    assert load_coops_frame(conn) is None


def test_loads_sro_rows():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_sro (address, building_name, owner, operator, "
        "occupancy_status, registered_rooms, latitude, longitude, ingested_at) "
        "VALUES ('100 main st', 'Main Rooms', 'Owner Co', 'Op Co', 'Open', 42, "
        "49.28, -123.1, 'now')"
    )
    conn.commit()
    df = load_sro_frame(conn)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["address"] == "100 main st"
    assert row["owner"] == "Owner Co"
    # Returned under the matcher body's name, not the table's — see Interfaces.
    assert row["#_registered_rooms"] == 42
    assert "registered_rooms" not in df.columns
    assert {"operator_group", "ownership_group", "raw_sro_id"} <= set(df.columns)


def test_loads_coop_rows():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, "
        "ownership_model, website, ingested_at) "
        "VALUES ('Elm Co-op', '300 elm st', 49.3, -123.2, 'Active', "
        "'Leasehold', 'https://example.org', 'now')"
    )
    conn.commit()
    df = load_coops_frame(conn)
    assert len(df) == 1
    assert df.iloc[0]["title"] == "Elm Co-op"
    assert "raw_coop_id" in df.columns


def test_secondary_address_index_maps_to_primary_addr_key():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_buildings (address, secondary_addresses, ingested_at) "
        "VALUES ('100 main st', '102 main st; 104 main st', 'now')"
    )
    conn.commit()
    idx = load_secondary_address_index(conn)
    assert idx["102 main st"] == "100 main st"
    assert idx["104 main st"] == "100 main st"


def test_secondary_address_index_normalizes_like_the_matcher():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_buildings (address, secondary_addresses, ingested_at) "
        "VALUES ('100 Main Street', '102 Main Street, rear; 104 Main Avenue', 'now')"
    )
    conn.commit()
    idx = load_secondary_address_index(conn)
    # Keys go through addr_key_from_freeform, not plain lowercasing:
    # "Street" -> "st", "Avenue" -> "ave".
    assert idx["104 main ave"] == "100 main st"
    # Split on ";" only — a comma inside one entry does not split it.
    assert idx["102 main st, rear"] == "100 main st"
    assert len(idx) == 2


def test_secondary_address_index_ignores_blank_values():
    conn = _conn()
    conn.execute(
        "INSERT INTO raw_buildings (address, secondary_addresses, ingested_at) "
        "VALUES ('100 main st', '', 'now')"
    )
    conn.commit()
    assert load_secondary_address_index(conn) == {}


def test_boundary_feature_collection_reads_geojson(tmp_path):
    p = tmp_path / "local-area-boundary.geojson"
    p.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Downtown"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                        },
                    }
                ],
            }
        )
    )
    fc = load_boundary_feature_collection(str(p))
    assert fc["features"][0]["properties"]["name"] == "Downtown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_overlay_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sica_core.ingest.overlay_sources'`

- [ ] **Step 3: Write the module**

```python
"""SQLite-backed inputs for the overlay matcher.

Replaces the CSV reads that `sica_mapping/data/overlays.py` did at render
time: the SRO/co-op/rezoning sources and buildings' secondary addresses all
already live in SQLite (raw_sro, raw_coops, raw_rezoning, raw_buildings), so
the matcher reads them from there instead of re-parsing the source files.

The neighbourhood boundaries are the one input still read from disk — they
come from `local-area-boundary.geojson`, which the fetcher already downloads
(see fetch/cov_open_data.py), and are a straight passthrough rather than
something derived into a table.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from ..normalize import addr_key_from_freeform


def _frame_or_none(conn: sqlite3.Connection, sql: str) -> pd.DataFrame | None:
    df = pd.read_sql_query(sql, conn)
    return None if df.empty else df


def load_sro_frame(conn: sqlite3.Connection) -> pd.DataFrame | None:
    return _frame_or_none(
        conn,
        """
        SELECT raw_sro_id, address, secondary_address, building_name, owner,
               operator, operator_group, ownership_group, occupancy_status,
               registered_rooms AS "#_registered_rooms", latitude, longitude
        FROM raw_sro
        """,
    )


def load_coops_frame(conn: sqlite3.Connection) -> pd.DataFrame | None:
    return _frame_or_none(
        conn,
        """
        SELECT raw_coop_id, title, address, lat, lon, status, ownership_model,
               website, read_more_url
        FROM raw_coops
        """,
    )


def load_rezoning_frame(conn: sqlite3.Connection) -> pd.DataFrame | None:
    return _frame_or_none(conn, "SELECT * FROM raw_rezoning")


def load_secondary_address_index(conn: sqlite3.Connection) -> dict[str, str]:
    """secondary-address addr_key -> owning building's own addr_key.

    A faithful port of `overlays.py::_load_secondary_address_index`, reading
    raw_buildings instead of buildings.csv (same rows — buildings.csv is
    raw_buildings' source). Keys go through the same addr_key_from_freeform
    the matcher uses elsewhere, split on ";" only. Feeds the co-op/SRO
    fallback for buildings the source lists under a different entrance.
    """
    df = pd.read_sql_query(
        "SELECT address, secondary_addresses FROM raw_buildings", conn
    )
    index: dict[str, str] = {}
    for primary, secs in zip(df["address"], df["secondary_addresses"]):
        if secs is None or (isinstance(secs, float) and pd.isna(secs)):
            continue
        secs = str(secs).strip()
        if not secs:
            continue
        primary_key = addr_key_from_freeform(primary)
        for sec_addr in secs.split(";"):
            sec_addr = sec_addr.strip()
            if not sec_addr:
                continue
            # First building to claim a given secondary address wins; a
            # genuine collision is a data question, not something to silently
            # pick a "better" side of here.
            index.setdefault(addr_key_from_freeform(sec_addr), primary_key)
    return index


def load_boundary_feature_collection(path: str | Path) -> dict:
    """Read local-area-boundary.geojson straight off disk (passthrough)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_overlay_sources.py -v`
Expected: 7 passed

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: 39 passed

- [ ] **Step 6: Commit** *(ask first)*

```bash
git add src/sica_core/ingest/overlay_sources.py tests/test_overlay_sources.py
git commit -m "Add SQLite-backed input loaders for the overlay matcher"
```

---

### Task 4: Move the matcher into sica_core

A move, not a rewrite. The address-matching heuristics must survive unchanged — the loose-key index, the direction / range / unit-prefix regex variants, the secondary-address fallback, and the point-in-polygon local-area resolution.

**Files:**
- Create: `src/sica_core/ingest/overlays.py` (from `src/sica_mapping/data/overlays.py`)
- Test: `tests/test_overlay_matching.py`

**Interfaces:**
- Consumes: Task 3's loaders.
- Produces: `match_overlays(conn, buildings_df, boundary_path) -> OverlayMatchResult`, where `OverlayMatchResult` is a dataclass with `matched: pd.DataFrame` (one row per building with overlay flags/detail columns, keyed by `addr_key`) and `unmatched: list[dict]` (rows destined for `overlay_housing`).

- [ ] **Step 1: Copy the module verbatim**

```bash
cp src/sica_mapping/data/overlays.py src/sica_core/ingest/overlays.py
```

Do not edit `src/sica_mapping/data/overlays.py` in this task — the renderer keeps using it until the follow-on plan, and Task 5 compares the two.

- [ ] **Step 2: Rewire the copy's inputs and outputs**

In `src/sica_core/ingest/overlays.py` make exactly these changes and nothing else:

1. Replace the module docstring's reference to render-time CSV reads with a note that it runs at ingest time against SQLite.
2. **Fix the imports — the copy will not import as-is.** The original's line `from ..core import addr_key_from_freeform, logger, normalize_cols, read_any_csv` resolves to `sica_core.core` once copied, which does not exist (ImportError). Replace it with:

```python
import logging

from ..normalize import addr_key_from_freeform

logger = logging.getLogger("sica_core.ingest.overlays")
```

   `sica_core.normalize.addr_key_from_freeform` is byte-identical to `sica_mapping`'s (verified with `diff`). `normalize_cols` and `read_any_csv` are only used by the two CSV loaders deleted in the next item, so they are dropped, not re-imported. Never import from `sica_mapping` (Global Constraints).

3. Delete `_load_optional_csv` and `_load_secondary_address_index`; import the Task 3 equivalents instead:

```python
from .overlay_sources import (
    load_boundary_feature_collection,
    load_coops_frame,
    load_rezoning_frame,
    load_secondary_address_index,
    load_sro_frame,
)
```

4. Replace `OverlayResult` with:

```python
@dataclass
class OverlayMatchResult:
    matched: pd.DataFrame
    unmatched: list[dict] = field(default_factory=list)
```

5. Replace the `match_overlays` signature and its input-loading preamble:

```python
def match_overlays(
    conn: sqlite3.Connection,
    buildings_df: pd.DataFrame,
    boundary_path: str,
) -> OverlayMatchResult:
    df = buildings_df.copy()
    addr_keys = set(df["addr_key"])
    boundary_polys = _build_boundary_polys(load_boundary_feature_collection(boundary_path))
    secondary_index = load_secondary_address_index(conn)
    loose_index = _build_loose_index(addr_keys)
    coops = load_coops_frame(conn)
    sro = load_sro_frame(conn)
    rezoning = load_rezoning_frame(conn)
```

   Everything downstream of these lines — every `_match_key`, `_address_key_variants`, `_coop_street`, `_rezoning_addr_key` call and the flag-setting loops — stays exactly as it is.

6. Replace the tail. Instead of calling `_append_extra_housing` to concatenate synthetic rows onto the frame, return them separately:

```python
    return OverlayMatchResult(matched=df, unmatched=list(extras.values()))
```

7. Delete `_append_extra_housing` entirely. Its `local_area` resolution moves into Task 5's writer; its column-defaulting behaviour (`text_cols` fillna, boolean coercion) applies only to the concatenated frame, which no longer exists here.

- [ ] **Step 3: Write the test**

```python
# tests/test_overlay_matching.py
import json
import sqlite3

import pandas as pd

from sica_core.db import init_db
from sica_core.ingest.overlays import match_overlays


def _boundary(tmp_path):
    p = tmp_path / "local-area-boundary.geojson"
    p.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Downtown"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-123.2, 49.2],
                                    [-123.2, 49.4],
                                    [-123.0, 49.4],
                                    [-123.0, 49.2],
                                    [-123.2, 49.2],
                                ]
                            ],
                        },
                    }
                ],
            }
        )
    )
    return str(p)


def _buildings():
    return pd.DataFrame(
        {
            "addr_key": ["100 main st"],
            "address": ["100 main st"],
            "lat": [49.28],
            "lon": [-123.1],
            "local_area": ["Downtown"],
        }
    )


def test_matched_sro_sets_flag_on_the_building(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_sro (address, owner, operator, ownership_group, "
        "occupancy_status, registered_rooms, latitude, longitude, ingested_at) "
        "VALUES ('100 Main Street', 'Owner Co', 'Op Co', 'Holding Group', 'Open', "
        "42, 49.28, -123.1, 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert result.unmatched == []
    row = result.matched.iloc[0]
    assert bool(row["is_sro"]) is True
    assert row["sro_owner"] == "Owner Co"
    # These two travel through loader columns whose names differ from the
    # table's; a mismatch blanks them silently, so assert them explicitly.
    assert row["sro_registered_rooms"] == "42"
    assert row["sro_ownership_group"] == "Holding Group"


def test_unmatched_coop_becomes_an_unmatched_record(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
        "VALUES ('Elm Co-op', '999 Nowhere Rd', 49.3, -123.15, 'Active', 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert len(result.unmatched) == 1
    rec = result.unmatched[0]
    assert rec["is_coop"] is True
    assert rec["housing_name"] == "Elm Co-op"
    assert rec["lat"] == 49.3


def test_secondary_address_fallback_matches(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_buildings (address, secondary_addresses, ingested_at) "
        "VALUES ('100 main st', '102 main st', 'now')"
    )
    conn.execute(
        "INSERT INTO raw_sro (address, owner, latitude, longitude, ingested_at) "
        "VALUES ('102 Main Street', 'Owner Co', 49.28, -123.1, 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert result.unmatched == []
    assert bool(result.matched.iloc[0]["is_sro"]) is True


def test_record_without_coordinates_is_skipped(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, status, ingested_at) "
        "VALUES ('Ghost Co-op', '999 Nowhere Rd', 'Active', 'now')"
    )
    conn.commit()

    result = match_overlays(conn, _buildings(), _boundary(tmp_path))

    assert result.unmatched == []
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_overlay_matching.py -v`
Expected: 4 passed. If `test_secondary_address_fallback_matches` fails, the `_loose_key`/`_address_key_variants` path was altered during the move — diff `src/sica_core/ingest/overlays.py` against `src/sica_mapping/data/overlays.py` and restore any accidental change.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: 43 passed

- [ ] **Step 6: Commit** *(ask first)*

```bash
git add src/sica_core/ingest/overlays.py tests/test_overlay_matching.py
git commit -m "Port overlay matching into sica_core, reading sources from SQLite"
```

---

### Task 5: Run overlays during ingest and verify against the fingerprint

Wires the matcher into `run_ingest()` and writes its two outputs: flags onto `buildings`, unmatched records into `overlay_housing`. Then checks the whole thing against Task 1's baseline and deletes the throwaway harness.

**Files:**
- Create: `src/sica_core/ingest/overlay_write.py`
- Modify: `src/sica_core/schema.sql` (overlay columns on `buildings`)
- Modify: `src/sica_core/ingest/__init__.py:97` (after the `buildings` merge step)
- Modify: `src/sica_core/config.py` (add `local_area_boundary_geojson`)
- Delete: `scripts/overlay_fingerprint.py`, `tests/test_overlay_fingerprint.py`, `tests/fixtures/overlay_fingerprint_baseline.json`
- Test: `tests/test_overlay_write.py`

**Interfaces:**
- Consumes: Task 4's `match_overlays(conn, buildings_df, boundary_path) -> OverlayMatchResult`.
- Produces: `ingest_overlays(conn, boundary_path) -> int` — returns the number of rows written to `overlay_housing`. Registered in `run_ingest` under the source name `overlays`.

- [ ] **Step 1: Add overlay columns to `buildings` in schema.sql**

Append to the `buildings` CREATE TABLE, before `created_at`. These are **all 18** columns the matcher initialises on the buildings frame (`overlays.py`, the `df[...] = ` block at the top of `match_overlays`) — persist every one. Six of them have no consumer today (`sro_operator_group`, `sro_ownership_group`, `rezoning_status_group`, `rezoning_category`, `rezoning_status_detail`, `rezoning_link`), but dropping matcher output at the persistence boundary is exactly the loss this port exists to prevent, and `sro_ownership_group` is ownership data the redesigned popup (spec §7) leads with.

```sql
    is_coop INTEGER NOT NULL DEFAULT 0,
    coop_status TEXT,
    coop_ownership_model TEXT,
    coop_url TEXT,
    housing_name TEXT,
    is_sro INTEGER NOT NULL DEFAULT 0,
    sro_owner TEXT,
    sro_operator TEXT,
    sro_operator_group TEXT,
    sro_ownership_group TEXT,
    sro_occupancy_status TEXT,
    sro_registered_rooms TEXT,
    is_rezoning INTEGER NOT NULL DEFAULT 0,
    rezoning_status TEXT,
    rezoning_status_group TEXT,
    rezoning_category TEXT,
    rezoning_status_detail TEXT,
    rezoning_link TEXT,
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_overlay_write.py
import json
import sqlite3

from sica_core.db import init_db
from sica_core.ingest.overlay_write import ingest_overlays


def _boundary(tmp_path):
    p = tmp_path / "local-area-boundary.geojson"
    p.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Downtown"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-123.2, 49.2],
                                    [-123.2, 49.4],
                                    [-123.0, 49.4],
                                    [-123.0, 49.2],
                                    [-123.2, 49.2],
                                ]
                            ],
                        },
                    }
                ],
            }
        )
    )
    return str(p)


def _seed_building(conn):
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, "
        "created_at, updated_at) "
        "VALUES ('100 main st', '100 main st', 49.28, -123.1, 'Downtown', 'now', 'now')"
    )


def test_matched_record_sets_flags_on_buildings(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.execute(
        "INSERT INTO raw_sro (address, owner, ownership_group, latitude, longitude, "
        "ingested_at) VALUES ('100 Main Street', 'Owner Co', 'Holding Group', "
        "49.28, -123.1, 'now')"
    )
    conn.commit()

    written = ingest_overlays(conn, _boundary(tmp_path))

    assert written == 0
    row = conn.execute(
        "SELECT is_sro, sro_owner, sro_ownership_group FROM buildings "
        "WHERE addr_key = '100 main st'"
    ).fetchone()
    assert row == (1, "Owner Co", "Holding Group")


def test_unmatched_record_lands_in_overlay_housing(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
        "VALUES ('Elm Co-op', '999 Nowhere Rd', 49.3, -123.15, 'Active', 'now')"
    )
    conn.commit()

    written = ingest_overlays(conn, _boundary(tmp_path))

    assert written == 1
    row = conn.execute(
        "SELECT addr_key, housing_name, is_coop, local_area FROM overlay_housing"
    ).fetchone()
    assert row[1] == "Elm Co-op"
    assert row[2] == 1
    assert row[3] == "Downtown"


def test_buildings_count_is_unaffected_by_unmatched_records(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
        "VALUES ('Elm Co-op', '999 Nowhere Rd', 49.3, -123.15, 'Active', 'now')"
    )
    conn.commit()

    ingest_overlays(conn, _boundary(tmp_path))

    assert conn.execute("SELECT COUNT(*) FROM buildings").fetchone()[0] == 1


def test_rerun_replaces_rather_than_duplicates(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_building(conn)
    conn.execute(
        "INSERT INTO raw_coops (title, address, lat, lon, status, ingested_at) "
        "VALUES ('Elm Co-op', '999 Nowhere Rd', 49.3, -123.15, 'Active', 'now')"
    )
    conn.commit()

    ingest_overlays(conn, _boundary(tmp_path))
    ingest_overlays(conn, _boundary(tmp_path))

    assert conn.execute("SELECT COUNT(*) FROM overlay_housing").fetchone()[0] == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_overlay_write.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sica_core.ingest.overlay_write'`

- [ ] **Step 4: Write the writer**

```python
"""Run overlay matching at ingest time and persist both of its outputs.

Matched records set flags and detail columns on the building they matched.
Records that matched nothing go to `overlay_housing` — a companion table, not
appended to `buildings`, so `COUNT(*) FROM buildings` stays meaningful and the
unmatched count remains a visible data-quality metric (see schema.sql).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

import pandas as pd

from .overlays import match_overlays

logger = logging.getLogger("sica_core.ingest.overlays")

# Every column match_overlays() initialises on the buildings frame — keep
# this list in lockstep with that block, or matcher output is silently lost.
_BUILDING_OVERLAY_COLUMNS = [
    "is_coop",
    "coop_status",
    "coop_ownership_model",
    "coop_url",
    "housing_name",
    "is_sro",
    "sro_owner",
    "sro_operator",
    "sro_operator_group",
    "sro_ownership_group",
    "sro_occupancy_status",
    "sro_registered_rooms",
    "is_rezoning",
    "rezoning_status",
    "rezoning_status_group",
    "rezoning_category",
    "rezoning_status_detail",
    "rezoning_link",
]

_OVERLAY_HOUSING_COLUMNS = [
    "addr_key",
    "address",
    "housing_name",
    "local_area",
    "lat",
    "lon",
    "is_coop",
    "is_sro",
    "coop_status",
    "coop_ownership_model",
    "coop_url",
    "sro_owner",
    "sro_operator",
    "sro_operator_group",
    "sro_ownership_group",
    "sro_occupancy_status",
    "sro_registered_rooms",
    "source_row_ids",
]


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, bool):
        return int(value)
    return value


def ingest_overlays(conn: sqlite3.Connection, boundary_path: str) -> int:
    buildings = pd.read_sql_query(
        "SELECT building_id, addr_key, address, lat, lon, local_area FROM buildings",
        conn,
    )
    result = match_overlays(conn, buildings, boundary_path)

    matched = result.matched
    updates = []
    for _, row in matched.iterrows():
        values = [_clean(row.get(col)) for col in _BUILDING_OVERLAY_COLUMNS]
        updates.append((*values, int(row["building_id"])))

    set_sql = ", ".join(f"{col} = ?" for col in _BUILDING_OVERLAY_COLUMNS)
    ingested_at = datetime.now(timezone.utc).isoformat()

    with conn:
        conn.executemany(
            f"UPDATE buildings SET {set_sql} WHERE building_id = ?", updates
        )
        # Rebuildable in its own right: a re-run replaces the whole set rather
        # than appending, so re-running ingest without a full init_db() stays
        # idempotent.
        conn.execute("DELETE FROM overlay_housing")
        if result.unmatched:
            rows = []
            for rec in result.unmatched:
                rows.append(
                    tuple(_clean(rec.get(col)) for col in _OVERLAY_HOUSING_COLUMNS)
                    + (ingested_at,)
                )
            placeholders = ", ".join(["?"] * (len(_OVERLAY_HOUSING_COLUMNS) + 1))
            columns_sql = ", ".join(_OVERLAY_HOUSING_COLUMNS + ["ingested_at"])
            conn.executemany(
                f"INSERT INTO overlay_housing ({columns_sql}) VALUES ({placeholders})",
                rows,
            )

    logger.info(
        "Overlays: %d buildings flagged, %d unmatched records stored",
        int(matched[["is_coop", "is_sro", "is_rezoning"]].any(axis=1).sum()),
        len(result.unmatched),
    )
    return len(result.unmatched)
```

`local_area` for the unmatched records is resolved inside the matcher (Step 5),
not here — this writer only persists what the matcher returns.

- [ ] **Step 5: Resolve `local_area` for unmatched records**

`_append_extra_housing` used to do this; the matcher must now do it before returning. In `src/sica_core/ingest/overlays.py`, immediately before the `return OverlayMatchResult(...)` line added in Task 4, insert:

```python
    for rec in extras.values():
        rec["local_area"] = _resolve_local_area(
            rec.get("lat"), rec.get("lon"), boundary_polys
        )
```

`boundary_polys` is already in scope — it is built at the top of `match_overlays`
(Task 4, Step 2.5).

- [ ] **Step 6: Add the boundary GeoJSON path to config**

In `src/sica_core/config.py`, add the default constant next to `DEFAULT_DB_PATH`:

```python
DEFAULT_BOUNDARY_GEOJSON = "data/raw/cov_open_data/local-area-boundary.geojson"
```

and the field to `IngestConfig`, after `pid_address_map`:

```python
    # Neighbourhood boundaries, read straight off disk rather than ingested
    # into a table: the fetcher already downloads this GeoJSON (see
    # fetch/cov_open_data.py) and the overlay matcher needs it for the
    # point-in-polygon local_area lookup on records with no building match.
    local_area_boundary_geojson: str = DEFAULT_BOUNDARY_GEOJSON
```

Add the matching key to `config.toml` under `[paths]`:

```toml
local_area_boundary_geojson = "data/raw/cov_open_data/local-area-boundary.geojson"
```

`tests/test_data_layout.py` keeps `config.toml` and `DataPaths` in sync — if it
fails after this, add the path to `sica_core/paths.py` as the message directs.

- [ ] **Step 7: Register the step in `run_ingest`**

In `src/sica_core/ingest/__init__.py`, import `ingest_overlays` and add the call immediately after the `buildings` merge (the matcher needs `buildings.addr_key` to exist):

```python
    counts["overlays"] = run_source(
        conn, run_id, "overlays", ingest_overlays, conn,
        config.local_area_boundary_geojson,
    )
```

- [ ] **Step 8: Run the tests**

Run: `uv run pytest tests/test_overlay_write.py -v`
Expected: 4 passed

- [ ] **Step 9: Rebuild and compare against the frozen fingerprint**

**Do not re-run `scripts/overlay_fingerprint.py` for the "after" side.** That script calls `sica_mapping`'s *old* `match_overlays` on `reconstruct_points()` output — running it now would compare the old matcher against itself and verify nothing about the port. The "after" side must be read from what the *new* pipeline persisted: flagged `buildings` rows plus `overlay_housing` rows, which together correspond to the baseline's matched buildings plus synthetic rows.

```bash
uv run python -m sica_core.ingest --config config.toml
uv run python - <<'EOF'
import json, sqlite3, sys
import pandas as pd
sys.path.insert(0, "scripts")
from overlay_fingerprint import fingerprint_overlays

conn = sqlite3.connect("data/derived/sica_core.db")
after_df = pd.read_sql_query(
    "SELECT addr_key, local_area, is_coop, is_sro FROM buildings "
    "UNION ALL "
    "SELECT addr_key, local_area, is_coop, is_sro FROM overlay_housing",
    conn,
)
after = fingerprint_overlays(after_df)
base = json.load(open("tests/fixtures/overlay_fingerprint_baseline.json"))

print("baseline:", base["counts"])
print("after:   ", after["counts"])
base_keys = {tuple(k) for k in base["keys"]}
after_keys = {tuple(k) for k in after["keys"]}
only_base = sorted(base_keys - after_keys)
only_after = sorted(after_keys - base_keys)
print(f"keys only in baseline: {len(only_base)}   only after: {len(only_after)}")
for k in only_base[:20]:
    print("  - baseline", k)
for k in only_after[:20]:
    print("  + after   ", k)
EOF
```

Expected: identical `counts`, and zero keys only-in-baseline / only-after.

**If counts or keys differ, stop and investigate before deleting the harness** — it is the only evidence the port is faithful. A drop in `sro`/`coop` means the address-matching path changed during the move: diff `src/sica_core/ingest/overlays.py` against `src/sica_mapping/data/overlays.py`, and check Task 3's loaders return the column names the body reads. A key that differs only in `local_area` points at Step 5's resolution. Record the final baseline/after counts in the task report.

- [ ] **Step 10: Delete the throwaway harness**

```bash
git rm scripts/overlay_fingerprint.py tests/test_overlay_fingerprint.py \
       tests/fixtures/overlay_fingerprint_baseline.json
```

Leave the `[tool.pytest.ini_options]` `pythonpath` entry — drop `"scripts"` from it, keep `"src"`.

- [ ] **Step 11: Run the full suite**

Run: `uv run pytest -q`
Expected: 44 passed

- [ ] **Step 12: Commit** *(ask first)*

```bash
git add src/sica_core/schema.sql src/sica_core/ingest/overlay_write.py \
        src/sica_core/ingest/overlays.py src/sica_core/ingest/__init__.py \
        src/sica_core/config.py config.toml pyproject.toml tests/test_overlay_write.py
git commit -m "Run overlay matching at ingest time, writing unmatched records to overlay_housing"
```

Stage explicit paths only — never `git add -A` or `git add .`. The working tree
holds uncommitted design docs the user has chosen not to commit. If
`tests/test_data_layout.py` forced a change to `src/sica_core/paths.py` (Step 6),
add that path too. The Step 10 `git rm` deletions are already staged.

---

### Task 6: Union `overlay_housing` into the export with a real `source`

Fixes the defect in spec §5: `tables.py:33` hardcodes `source = "building"`, so all 5,281 exported rows claim to be buildings and the 153 unmatched records are indistinguishable from real ones.

**Files:**
- Modify: `src/sica_core/export.py:41-44` (`reconstruct_points`)
- Test: `tests/test_export_source_discriminator.py`

**Interfaces:**
- Consumes: `overlay_housing` (Task 2), populated by Task 5.
- Produces: `reconstruct_points()` returns a frame with a `source` column valued `building`, `overlay_sro` or `overlay_coop`, and `b_id` values that are unique across both origins.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_source_discriminator.py
import sqlite3

import pandas as pd

from sica_core.db import init_db
from sica_core.export import reconstruct_points


def _seed(conn):
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, "
        "created_at, updated_at) "
        "VALUES ('100 main st', '100 main st', 49.28, -123.1, 'Downtown', 50, 'now', 'now')"
    )
    conn.execute(
        "INSERT INTO overlay_housing (addr_key, address, housing_name, local_area, "
        "lat, lon, is_coop, is_sro, ingested_at) "
        "VALUES ('999 nowhere rd', '999 nowhere rd', 'Elm Co-op', 'Downtown', "
        "49.3, -123.15, 1, 0, 'now')"
    )
    conn.execute(
        "INSERT INTO overlay_housing (addr_key, address, housing_name, local_area, "
        "lat, lon, is_coop, is_sro, ingested_at) "
        "VALUES ('888 elsewhere st', '888 elsewhere st', 'Old Rooms', 'Downtown', "
        "49.31, -123.16, 0, 1, 'now')"
    )
    conn.commit()


def test_source_distinguishes_buildings_from_overlay_records():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    pts = reconstruct_points(conn, pd.Timestamp("2026-09-20", tz="UTC"))

    assert set(pts["source"]) == {"building", "overlay_coop", "overlay_sro"}
    assert (pts.loc[pts["source"] == "building", "addr_key"] == "100 main st").all()


def test_b_id_is_unique_across_both_origins():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    pts = reconstruct_points(conn, pd.Timestamp("2026-09-20", tz="UTC"))

    assert pts["b_id"].is_unique
    assert len(pts) == 3


def test_overlay_rows_have_no_units_or_owner():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    pts = reconstruct_points(conn, pd.Timestamp("2026-09-20", tz="UTC"))
    overlay = pts[pts["source"] != "building"]

    assert overlay["units"].isna().all()
    assert (overlay["owner_group"] == "(Unknown)").all()
    assert (overlay["member_count"] == 0).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export_source_discriminator.py -v`
Expected: FAIL — `KeyError: 'source'`

- [ ] **Step 3: Add the union to `reconstruct_points`**

At the top of `reconstruct_points`, after the `buildings` frame is built and renamed (currently line 53), add:

```python
    buildings["source"] = "building"
```

Then, immediately before the function returns, append the overlay rows:

```python
    merged = _append_overlay_housing(conn, merged)
```

And add the helper alongside `reconstruct_points`:

```python
def _append_overlay_housing(
    conn: sqlite3.Connection, points: pd.DataFrame
) -> pd.DataFrame:
    """Union `overlay_housing` onto the points frame.

    These are SRO/co-op source records that matched no building (see
    ingest/overlay_write.py). They carry coordinates, a name and a housing
    type and nothing else — no units, year built, assessed values or owner —
    so they are tagged with a real `source` value rather than being passed off
    as buildings. b_id continues from the buildings table's maximum so the two
    sets never collide.
    """
    overlay = pd.read_sql_query("SELECT * FROM overlay_housing", conn)
    if overlay.empty:
        return points

    first_id = int(pd.to_numeric(points["b_id"]).max()) + 1 if len(points) else 1
    overlay = overlay.rename(columns={"overlay_id": "_overlay_id"})
    overlay["b_id"] = range(first_id, first_id + len(overlay))
    overlay["source"] = [
        "overlay_coop" if bool(c) else "overlay_sro"
        for c in overlay["is_coop"]
    ]
    overlay["owner_group"] = "(Unknown)"
    overlay["owner_key"] = "unknown"
    overlay["member_count"] = 0
    overlay["member_count_all"] = 0
    overlay["has_vtu_member"] = False
    overlay["member_share_building"] = 0.0
    overlay["members_payload"] = [[] for _ in range(len(overlay))]

    combined = pd.concat([points, overlay], ignore_index=True)
    for col in ("is_coop", "is_sro", "is_rezoning", "has_vtu_member"):
        if col in combined.columns:
            combined[col] = combined[col].fillna(False).astype(bool)
    return combined
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_export_source_discriminator.py -v`
Expected: 3 passed

- [ ] **Step 5: Remove the hardcode in the renderer's table builder**

In `src/sica_mapping/data/tables.py:33`, replace:

```python
    tbl["source"] = "building"
```

with a passthrough of the real value, falling back only when the column is absent (the legacy CSV path never sets it):

```python
    tbl["source"] = pts_df["source"] if "source" in pts_df.columns else "building"
```

The function's parameter is `pts_df` (there is no `df` in scope). Do **not** add `"source"` to the column list `buildings_table` selects: the legacy CSV pipeline's frame has no `source` column, so selecting it would raise `KeyError` there. The assignment above aligns on index (`tbl` is a column subset copy of `pts_df`) and is all that is needed for `source` to reach `building_records.json`.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: 47 passed

- [ ] **Step 7: Rebuild and spot-check the export**

```bash
uv run python scripts/rebuild_map.py
python -c "
import json, collections
b = json.load(open('www/index_building_records.json'))
print(collections.Counter(r['source'] for r in b['records'].values()))
"
```

Expected: roughly `{'building': 5128, 'overlay_sro': 117, 'overlay_coop': 36}` — the exact split depends on the current data refresh, but `building` must equal the `buildings` table's row count.

**Then verify nothing is duplicated.** Until the renderer plan removes it, `build.py` still runs the old render-time `match_overlays` — now on a frame that already contains the `overlay_housing` rows. Those rows carry the exact `addr_key` the old matcher derives, so it should *match* them rather than append a second copy; this check turns that expectation into evidence:

```bash
uv run python - <<'EOF'
import json, sqlite3
from collections import Counter
recs = list(json.load(open("www/index_building_records.json"))["records"].values())
addr = Counter(r["address"] for r in recs)
dups = {k: n for k, n in addr.items() if n > 1}
n_buildings = sqlite3.connect("data/derived/sica_core.db").execute(
    "SELECT COUNT(*) FROM buildings").fetchone()[0]
print("records:", len(recs), " duplicate addresses:", len(dups),
      " b_id unique:", len({r["b_id"] for r in recs}) == len(recs))
print("source=building:", sum(r["source"] == "building" for r in recs),
      " buildings table:", n_buildings)
for k, n in list(dups.items())[:10]:
    print("  dup", k, n)
EOF
```

Expected: zero duplicate addresses, `b_id` unique, and `source=building` equal to the `buildings` table count. (Keyed on `address` because `building_records.json` does not carry `addr_key`; a render-time duplicate of an overlay row would repeat its source address exactly.) If duplicates appear, the render-time matcher is appending rows the export already supplied; report it rather than patching `build.py` — that call is removed in the renderer plan.

- [ ] **Step 8: Commit** *(ask first)*

```bash
git add src/sica_core/export.py src/sica_mapping/data/tables.py \
        tests/test_export_source_discriminator.py
git commit -m "Union overlay_housing into the export with a real source discriminator"
```

---

### Task 7: Complete the artifact set

Adds the three remaining contract changes from spec §4 so the artifacts are complete while Folium is still rendering them. The follow-on renderer plan consumes these.

**Files:**
- Modify: `src/sica_core/export.py` (`export_to_cache`, marker metadata)
- Modify: `src/sica_mapping/build.py:318-341` (read `lat`/`lon` through to metadata)
- Test: `tests/test_export_artifacts.py`

**Interfaces:**
- Produces: `export_artifacts(conn, out_dir, pid_address_map_path=None) -> None` writing `filter_config.json`, `marker_metadata.json`, `building_records.json`, `blocks.geojson`, and a copy of `local-area-boundary.geojson`. Each carries a top-level `schema_version` of `1`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_artifacts.py
import json
import sqlite3

from sica_core.db import init_db
from sica_core.export import export_artifacts


def _seed(conn):
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, "
        "year_built, created_at, updated_at) VALUES ('100 main st', '100 main st', "
        "49.28, -123.1, 'Downtown', 50, 1970, 'now', 'now')"
    )
    conn.execute(
        "INSERT INTO blocks (block_id, geom, ingested_at) VALUES (1, "
        "'{\"type\":\"Polygon\",\"coordinates\":[[[-123.2,49.2],[-123.2,49.4],"
        "[-123.0,49.4],[-123.0,49.2],[-123.2,49.2]]]}', 'now')"
    )
    conn.commit()


def test_writes_all_artifacts(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    export_artifacts(conn, tmp_path)

    for name in (
        "filter_config.json",
        "marker_metadata.json",
        "building_records.json",
        "blocks.geojson",
    ):
        assert (tmp_path / name).exists(), name


def test_copies_the_boundary_geojson_through(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)
    src = tmp_path / "src-boundary.geojson"
    src.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    out = tmp_path / "artifacts"

    export_artifacts(conn, out, boundary_geojson_path=str(src))

    copied = json.loads((out / "local-area-boundary.geojson").read_text())
    assert copied["type"] == "FeatureCollection"


def test_marker_metadata_carries_coordinates(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    export_artifacts(conn, tmp_path)

    meta = json.loads((tmp_path / "marker_metadata.json").read_text())
    assert meta["schema_version"] == 1
    record = meta["markers"][0]
    assert record["lat"] == 49.28
    assert record["lon"] == -123.1


def test_blocks_geojson_is_a_feature_collection(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    export_artifacts(conn, tmp_path)

    gj = json.loads((tmp_path / "blocks.geojson").read_text())
    assert gj["type"] == "FeatureCollection"
    feature = gj["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert "block_label" in feature["properties"]
    assert "member_share" in feature["properties"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export_artifacts.py -v`
Expected: FAIL — `ImportError: cannot import name 'export_artifacts'`

- [ ] **Step 3: Implement `export_artifacts`**

Add to `src/sica_core/export.py`, alongside the existing `export_to_cache` (which stays until the renderer plan removes it):

```python
SCHEMA_VERSION = 1


def export_artifacts(
    conn: sqlite3.Connection,
    out_dir: str | Path,
    pid_address_map_path: str | None = None,
    boundary_geojson_path: str | None = None,
    now: pd.Timestamp | None = None,
) -> None:
    """Write the complete frontend artifact set.

    This is the one-directional contract: every value the map displays is
    produced here. Each file carries a schema_version so a frontend built
    against an older shape fails loudly instead of rendering an empty map.
    """
    if now is None:
        now = pd.Timestamp.now(tz="UTC")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    points_df = reconstruct_points(conn, now, pid_address_map_path)
    blocks_df = reconstruct_blocks(conn, points_df)
    filter_cfg = reconstruct_filter_config(conn, points_df, blocks_df, now)

    _write_json(
        out_dir / "filter_config.json",
        {"schema_version": SCHEMA_VERSION, **filter_cfg},
    )
    _write_json(
        out_dir / "marker_metadata.json",
        {
            "schema_version": SCHEMA_VERSION,
            "markers": _marker_records(points_df),
        },
    )
    _write_json(
        out_dir / "building_records.json",
        {
            "schema_version": SCHEMA_VERSION,
            **_building_records(points_df),
        },
    )
    _write_json(out_dir / "blocks.geojson", _blocks_feature_collection(blocks_df))

    if boundary_geojson_path:
        shutil.copyfile(
            boundary_geojson_path, out_dir / "local-area-boundary.geojson"
        )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, separators=(",", ":"), default=str), encoding="utf-8"
    )


def _blocks_feature_collection(blocks_df: pd.DataFrame) -> dict:
    """Emit stored GeoJSON geometry directly — no shapely round trip.

    `blocks.geom` is already GeoJSON text in SQLite, so parsing it into a
    shapely object only to re-serialize via __geo_interface__ is wasted work.
    """
    property_cols = [
        "block_id",
        "buildings",
        "total_units",
        "median_year_built",
        "member_buildings",
        "total_members",
        "member_share",
        "local_area",
        "block_label",
    ]
    features = []
    for _, row in blocks_df.iterrows():
        geom = row.get("geom_geojson") or row.get("geom")
        if geom is None:
            continue
        if isinstance(geom, str):
            geom = json.loads(geom)
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    col: (None if pd.isna(row.get(col)) else row.get(col))
                    for col in property_cols
                    if col in blocks_df.columns
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "schema_version": SCHEMA_VERSION,
        "features": features,
    }
```

Add `import shutil` to the module's imports.

- [ ] **Step 4: Keep `reconstruct_blocks` geometry as text**

`reconstruct_blocks` currently drops `geom` and returns a shapely `geom_parsed`. Change its final lines to retain the raw string so `_blocks_feature_collection` can pass it through:

```python
    merged["block_label"] = assign_block_labels(merged)
    return merged  # keep `geom` (GeoJSON text) — callers that need shapely use geom_parsed
```

`export_to_cache` already drops `geom_parsed` before serializing; confirm it also drops `geom` so the legacy cache shape is unchanged.

- [ ] **Step 5: Add `lat`/`lon` to marker metadata**

In `src/sica_mapping/frontend/layout.py`, inside `add_buildings_layers`'s `marker_metadata.append({...})` block (line ~291), add two entries:

```python
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
```

`marker_var` stays for now — the renderer plan removes it once `bootstrap.js` keys markers by `b_id`.

- [ ] **Step 6: Write `_marker_records` and `_building_records`**

These mirror what `build.py:318-341` does today, moved into `sica_core`. Add to `export.py`:

```python
def _marker_records(points_df: pd.DataFrame) -> list[dict]:
    """Per-building styling records, including coordinates.

    Styling values (radius, colors, ring weights) are computed here rather
    than at render time so the frontend needs no styling logic of its own.
    """
    records = []
    for _, r in points_df.iterrows():
        has_member = bool(r.get("has_vtu_member"))
        records.append(
            {
                "b_id": int(r["b_id"]),
                "lat": None if pd.isna(r["lat"]) else float(r["lat"]),
                "lon": None if pd.isna(r["lon"]) else float(r["lon"]),
                "owner_key": r.get("owner_key"),
                "block_id": None if pd.isna(r.get("block_id")) else int(r["block_id"]),
                "units": None if pd.isna(r.get("units")) else int(r["units"]),
                "year_built": None
                if pd.isna(r.get("year_built"))
                else int(r["year_built"]),
                "local_area": r.get("local_area"),
                "is_vtu": has_member,
                "member_count": int(r.get("member_count") or 0),
                "housing_type": r.get("housing_type") or "",
                "source": r.get("source", "building"),
            }
        )
    return records


def _building_records(points_df: pd.DataFrame) -> dict:
    """Full per-building record set — the popup and the table both read this."""
    columns = [
        c
        for c in points_df.columns
        if c not in ("geom_parsed", "members_payload")
    ]
    records = {}
    for _, r in points_df.iterrows():
        rec = {
            c: (None if isinstance(r[c], float) and pd.isna(r[c]) else r[c])
            for c in columns
        }
        records[str(int(r["b_id"]))] = rec
    return {"columns": columns, "records": records}
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_export_artifacts.py -v`
Expected: 4 passed

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest -q`
Expected: 51 passed

- [ ] **Step 9: Verify the map still renders**

```bash
uv run python scripts/rebuild_map.py
test -f www/index.html && echo "map rendered"
```

Expected: `map rendered`. Open it and confirm markers, blocks and the sidebar all still work — this plan must not change what the map looks like.

- [ ] **Step 10: Commit** *(ask first)*

```bash
git add src/sica_core/export.py src/sica_mapping/frontend/layout.py \
        tests/test_export_artifacts.py
git commit -m "Emit the complete frontend artifact set from sica_core"
```

---

## Done when

- `match_overlays` runs at ingest time against SQLite; no CSV is read at render time for overlays.
- `overlay_housing` holds the unmatched records; `SELECT COUNT(*) FROM buildings` is unaffected by them.
- `building_records.json` carries a real `source` discriminator.
- `export_artifacts()` writes all five artifacts with `schema_version`.
- `uv run pytest -q` is green; `uv run python scripts/rebuild_map.py` still produces a working `www/index.html`.

## Next plan

The frontend split — spec §9 steps 4-8, **as revised 2026-09-21** (see the revision note at the top of the spec): scaffold a standalone `frontend/` Vite project, move `wiring.js` and the HTML fragments into it, write `bootstrap.ts`, port the block-style/legend/table logic and the popup redesign (spec §7) to TS, parity-check against the Folium build, then delete `sica_mapping` entirely and drop `folium`, and fix the CI and deploy workflows (spec §11). There is no Python `render()` — `rebuild_map.py` becomes ingest + export only.
