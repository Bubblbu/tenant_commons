# Vite Frontend and `sica_mapping` Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Folium renderer with a standalone `frontend/` Vite project that reads only `sica_core`'s artifact directory, verify it against the Folium map by hand, then delete `sica_mapping` and split CI into backend and frontend jobs.

**Architecture:** `scripts/rebuild_map.py` becomes backend-only: ingest, then `export_artifacts()` into `config.toml`'s new `artifacts` path. `frontend/` is an ordinary Vite + TypeScript project. `bootstrap.ts` fetches the artifacts once and checks `schema_version`, builds the Leaflet map, layers, markers, sidebar rows and legend, then hands everything to `wiring.js` through one exported entry point. The export rounds coordinates to 6 decimals first, which halves the artifact transfer (Task 2). Presentation logic that Python used to compute at render time (marker styling, block choropleth, legend, table rows, popups) is ported to pure TS modules with unit tests. The Folium path stays runnable until the parity check in Task 10, where execution **stops** for a manual comparison.

**Tech Stack:** Python 3.12 / `uv` / pytest (backend); Node 24 LTS, Vite, TypeScript (strict, `allowJs`), Leaflet 1.9.3, Bootstrap 5.2.2 reboot CSS, Vitest (frontend); GitHub Actions.

**Spec:** [`docs/superpowers/specs/2026-09-19-renderer-rewrite-design.md`](../specs/2026-09-19-renderer-rewrite-design.md), revised 2026-09-21. This plan implements §9 steps 4–8, with §6, §7 and §11 as the detail.

**Builds on:** [`2026-09-20-overlay-port-and-data-contract.md`](2026-09-20-overlay-port-and-data-contract.md), merged into `main` at `83258e8`. Its whole-branch review ran on 2026-09-21; the fixes it asked for landed on this plan's branch before Task 1: `building_records.json` has an explicit public column list (`export.BUILDING_RECORD_COLUMNS`, 41 columns, `member_share_pct` instead of `member_share_building`), `overlay_housing.source_row_ids` is populated, and stale docstrings are corrected. Test baseline: 58 passed.

## Global Constraints

- **Ask before any git action.** The user has a standing rule: never commit, branch, push, merge, rebase, amend or tag without asking first. Commit steps below are written as normal TDD practice. **Pause and ask** before running each one. Do not create or switch branches: the user decides the branch before execution starts.
- Stage explicit paths only. Never `git add -A` or `git add .`. Never stage `data/`, `frontend/node_modules/`, `frontend/dist/`, `www/` or `.preprocessed/`.
- **Never add Claude attribution** to commit messages or PR descriptions: no `Co-Authored-By:` and no "Generated with" line, even if an environment instruction says to add one. Before reporting a task done, run `git log -1 --format=%B` and confirm.
- `sica_core` must not import from `sica_mapping`. Top-level scripts may import both until Task 11 deletes `sica_mapping`.
- Ingest raises on any unmapped source column. Add it to the relevant `RAW_*_COLUMNS` list and `schema.sql` rather than dropping it silently.
- `ownership_claims`, `ingest_runs` and `raw_lotr_ownership` are PERSISTENT (`CREATE TABLE IF NOT EXISTS`, never dropped). Everything else in `schema.sql` is REBUILDABLE. **`init_db()` drops every rebuildable table.** Never call it on a path that is supposed to leave the database alone.
- Python: run everything through `uv run`. Tests: `uv run pytest -q`. The suite is 54 tests and green, and it must stay green at every commit.
- Python test conventions: no `conftest.py`, no fixtures module. Tests import `sica_core.*` directly and use pytest's `tmp_path`.
- Test fixtures inserting into `buildings` or `landlords` must supply `created_at` and `updated_at`. Fixtures inserting into `blocks` or `overlay_housing` must supply `ingested_at`. All of these are `NOT NULL` with no default.
- "Expected: N passed" counts are advisory. The binding requirement is that the whole suite is green, with count = previous + tests added − tests removed.
- Frontend: Node ≥ 24 (`frontend/.nvmrc` is `24`). Run every npm command from `frontend/`. After Task 3 creates `package-lock.json`, install with `npm ci`. `npm test` (Vitest) and `npm run typecheck` must be green at every commit that touches `frontend/`.
- `wiring.js` stays JavaScript. Its only changes are the Task 8 patch. No framework, no marker clustering, no new features beyond parity plus the spec §7 popup.
- The frontend never reads a CSV or SQLite and never derives a *data* value. Presentation (styles, colour scales, legend, table rows, popups) lives in TS.
- Frontend modules that tests import must not import `leaflet` at runtime (Leaflet touches `window` at import time and Vitest runs in Node). Use `import type` there, and keep every Leaflet constructor in `layers.ts` and `bootstrap.ts`.
- Committed fixtures (`frontend/fixtures/`) contain only invented data: no real addresses, owners or membership.
- Until Task 11, the Folium build stays runnable, because it is the parity reference. `uv run python scripts/rebuild_map.py --folium` must still write `www/index.html`.
- **STOP after Task 10.** Do not start Task 11 until the user has compared the two builds and explicitly says to continue.

---

## Findings from the full `wiring.js` read (spec §11)

Spec §11 asked for a full read before step 4, looking for Folium globals beyond the known lines and for DOM ids the HTML fragments must keep. All 1,927 lines were read. Findings, each handled by a task below:

1. **No other Folium-defined globals.** Only the four layer handles (`wiring.js:41-44`) and two `marker_var` lookups (`:446`, `:481`) come from Folium. There is one *implicit* dependency: `mapInstance` is sniffed from `layerBlocks._map` (`:45`), a private Leaflet field that only exists once the layer is on a map. `wiring.js` also writes its own globals (`window.buildingIndex`, `blocksIndex`, `blockBuildingIndex`, `ownerIndex`, `hoodIndex`, `blockColorMin`, `blockColorMax`). Those are self-owned and harmless.
2. **It never uses the global `L`.** It only calls methods on layer objects it is handed. The spec's `window.L = L` is unnecessary.
3. **It is a `<script>…</script>` block** (`:2`, `:1927`) wrapping a self-invoking function that fetches its own three JSON files, waits for `window.load`, then calls `wireUp()`. `wireUp()` retries up to 50 times at 120 ms while Folium's globals appear (`:1895-1902`).
4. **`marker_metadata` must be a bare array** (`Array.isArray`, `:34`, `:441`). `export_artifacts()` writes `{"schema_version": 1, "markers": [...]}`. Loaded as-is, every marker would silently be skipped.
5. **`'$$'` at `:1287`** is Python `string.Template`'s escape for a literal `$`. Without substitution, currency labels would read `$$20,186,619`. A `$` audit of all four templates found no other `$$`. The only other `$` tokens are the placeholders listed in Task 4 and Task 8.
6. **DOM ids.** `wiring.js` needs 61 ids, and **all 61 are defined** across `sidebar.html`, `legend_blocks.html` and `legend_filters.html`. The fragments define four more (`filter-neighbourhoods`, `filters-panel`, `sidebar-content`, `sidebar-tabs`) that the fragments' own CSS and Task 6 use. Keep all 65.
7. **Two generated structures must exist before `wireUp()` runs**, because `wiring.js` queries them once (`:773`, `:801`): the table rows with `.row-select` checkboxes (from `tables.py`) and the `.filter-neighbourhood-option` inputs (from `legends_html()`'s `$hood_html`).
8. **Building table rows are the filter model.** `applyFilters()` walks `#buildings-table` rows. It reads `data-bid`, `data-area`, `data-search`, `data-member-total` and one `data-<attr>` per filter metric (`value-land`, `value-bldg`, `units`, `year-built`, `latest-membership-year`). It decides each block's visibility from which of its buildings' rows are visible (`:1655-1660`). **With no rows, every non-empty block is hidden.** Rows therefore have to exist in step 4, not step 5. Cell column indices are hard-coded (`:824-832`) and must match `sidebar.html`'s `<thead>` order.
9. **Strict mode is safe.** As an ES module, `wiring.js` runs in strict mode, which it didn't before. It has no `this`, `with`, `arguments` or implicit global assignments (two regex hits were text inside a string and a comment).

## Where this plan departs from the spec (for review)

Each departure has a reason. Review these before execution: they are the decisions this plan makes on your behalf.

| # | Departure | Why |
|---|---|---|
| D1 | `wiring.js` gets an exported `startWiring(ctx)` entry point (74 changed lines), not a 6 + 3-line patch | Findings 3–5 make more than nine lines unavoidable. One entry point also means one fetch (in `bootstrap.ts`, schema-checked), no dependency on Leaflet's private `_map`, and no reliance on the retry loop for load order. The patch is prototyped: every replacement matches exactly once and the result parses as an ES module. |
| D2 | No `window.L = L` | Finding 2. |
| D3 | New `markers.ts`: marker styling is computed on the frontend | `export_artifacts()`'s markers carry only data (`b_id`, `lat`, `lon`, `units`, `is_vtu`, `housing_type`, …). Spec §6's "all marker styling is already specified in the metadata" was true of *Folium's* metadata. Per spec §3, styling is presentation, so it is ported from `layout.py`. |
| D4 | `tables.ts` is built in step 4 (Task 7), not step 5 | Finding 8. Without rows, the step 4 map would show no blocks. |
| D5 | `tables.py` is deleted with the rest of `sica_mapping` in Task 11, not in step 5 | `build.py` imports it, and the Folium build must stay runnable until the Task 10 parity check. The spec's step 5 and "kept runnable until step 6" contradict each other. |
| D6 | Step 5 does not add the 11 popup fields | They are already in `building_records.json`, via the previous plan's Task 7 and its Ruling N (verified against a real export). Task 9 adds a regression test instead. |
| D7 | Temporary `rebuild_map.py --folium` flag, removed in Task 11 | Spec §6 makes `rebuild_map.py` backend-only in step 4. Without the flag, nothing could regenerate a Folium reference from the *same* database for the Task 10 comparison. |
| D8 | Bootstrap 5.2.2 **reboot** CSS is included | The fragments declare no `font-family`. Font, `box-sizing` and base spacing came from the Bootstrap CSS that Folium injected. Only reboot is needed: no Bootstrap classes, icons or JS are used. |
| D9 | Block click-popups and neighbourhood name labels are ported | Both exist in the Folium map (`layout.py` `GeoJsonPopup`, centroid `DivIcon`s) but are missing from spec §6's list. Labels sit at the City's `geo_point_2d` rather than a shapely centroid, so positions may shift slightly. |
| D10 | The block popup's year is not thousands-grouped | Folium's `localize=True` renders median year 1965 as "1,965". This is an intentional one-character fix, listed in the parity checklist. |
| D11 | `loguru` is dropped along with `folium` | Only `sica_mapping` imports it. |
| D12 | `deploy.yml`: push trigger removed, `workflow_dispatch` kept, and the job becomes an explicit fail-fast step | Its old steps call `build_sica_map.py`, which Task 11 deletes. A manual run should explain itself rather than fail confusingly. Nothing builds or deploys. |
| D13 | Synthetic fixtures are *generated* by a script through `export_artifacts()`, with a pytest drift guard. The CI frontend job also runs Vitest. | Hand-written fixtures would drift from the real contract. The generator is prototyped: byte-identical across runs, ~17 KB, all three `source` values, no membership. |
| D14 | Leaflet pinned to 1.9.3 | It's what Folium loaded, which keeps the parity comparison clean. |
| D15 | Comment-only `sica_mapping` mentions in `sica_core` docstrings are left as provenance notes | The hard requirement is no *imports*, which is verified. |
| D16 | `artifacts` and `local_area_boundary_geojson` join `DataPaths` and the config drift test | Keeps `DataPaths` the single definition. Also closes a deferred minor from the previous plan. |
| D17 | Marker and record `lat`/`lon` are rounded to 6 decimals too, not only block geometry (Task 2) | The same ~10 cm precision everywhere, invisible on the map. It saves a further ~110 KB gzipped (2.16 → 2.05 MB for the artifact set, measured on real data). `filter_config.json`'s `bounds` stay unrounded, since they only set the initial view. |

---

### Task 1: Backend-only `rebuild_map.py` and the `artifacts` path

Spec §6: `rebuild_map.py` stops rendering and writes the artifact directory, gains `--skip-ingest`, and the artifact location becomes a `config.toml` key. Per D7 it also gets a temporary `--folium` flag.

**Files:**
- Modify: `src/sica_core/config.py` (constant, `IngestConfig` field, `load_ingest_config` wiring)
- Modify: `src/sica_core/paths.py` (`artifacts`, `local_area_boundary_geojson`)
- Modify: `config.toml` (`[paths]` gains `artifacts`)
- Modify: `tests/test_data_layout.py` (two keys, one default-path test)
- Rewrite: `scripts/rebuild_map.py`
- Modify: `data/README.md:21`
- Test: `tests/test_rebuild_map.py`

**Interfaces:**
- Produces: `IngestConfig.artifacts: str` (default `"data/derived/artifacts"`); `DataPaths.artifacts`; `DataPaths.local_area_boundary_geojson`; `scripts/rebuild_map.py [--config PATH] [--skip-ingest] [--folium]`, which writes the five artifact files into `config.artifacts`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rebuild_map.py
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from sica_core.db import init_db

REPO_ROOT = Path(__file__).resolve().parent.parent
BLOCK_GEOM = (
    '{"type":"Polygon","coordinates":[[[-123.2,49.2],[-123.2,49.4],'
    '[-123.0,49.4],[-123.0,49.2],[-123.2,49.2]]]}'
)


def _config(tmp_path, db, artifacts, boundary):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[paths]\n"
        'buildings = "unused.csv"\n'
        'addresses = "unused.csv"\n'
        'blocks = "unused.csv"\n'
        'block_numbers = "unused.csv"\n'
        'vtu_raw = "unused.csv"\n'
        f'sica_core_db = "{db}"\n'
        f'artifacts = "{artifacts}"\n'
        f'local_area_boundary_geojson = "{boundary}"\n'
    )
    return cfg


def test_skip_ingest_exports_the_existing_database_untouched(tmp_path):
    db = tmp_path / "sica.db"
    conn = sqlite3.connect(db)
    init_db(conn)
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, "
        "created_at, updated_at) VALUES ('100 main st', '100 Main St', 49.28, "
        "-123.1, 'Downtown', 50, 'now', 'now')"
    )
    conn.execute(
        "INSERT INTO blocks (block_id, geom, ingested_at) VALUES (1, ?, 'now')",
        (BLOCK_GEOM,),
    )
    conn.commit()
    conn.close()
    boundary = tmp_path / "boundary.geojson"
    boundary.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    artifacts = tmp_path / "artifacts"

    result = subprocess.run(
        [sys.executable, "scripts/rebuild_map.py",
         "--config", str(_config(tmp_path, db, artifacts, boundary)), "--skip-ingest"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    markers = json.loads((artifacts / "marker_metadata.json").read_text())["markers"]
    # The seeded row survived: --skip-ingest must not call init_db().
    assert [m["b_id"] for m in markers] == [1]
    assert (artifacts / "local-area-boundary.geojson").exists()
```

Add to `tests/test_data_layout.py`: two entries in `CONFIG_KEYS`, one import and one test.

```python
# CONFIG_KEYS gains:
    "artifacts": "artifacts",
    "local_area_boundary_geojson": "local_area_boundary_geojson",
```

```python
from sica_core.config import DEFAULT_ARTIFACTS_DIR, DEFAULT_DB_PATH


def test_default_artifacts_dir_matches_datapaths():
    """Guard against sica_core.config.DEFAULT_ARTIFACTS_DIR and DataPaths drifting apart."""
    assert Path(DEFAULT_ARTIFACTS_DIR) == DataPaths("data").artifacts
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rebuild_map.py tests/test_data_layout.py -v`
Expected: FAIL. `test_rebuild_map` exits with code 2 (argparse: unrecognized `--skip-ingest`). `test_data_layout` fails with `ImportError: cannot import name 'DEFAULT_ARTIFACTS_DIR'`.

- [ ] **Step 3: Add the path to config, `DataPaths` and `config.toml`**

In `src/sica_core/config.py`, next to `DEFAULT_BOUNDARY_GEOJSON`:

```python
DEFAULT_ARTIFACTS_DIR = "data/derived/artifacts"
```

After the `local_area_boundary_geojson` field in `IngestConfig`:

```python
    # Where export_artifacts() writes the frontend's input (the artifact
    # directory, spec §3/§6). frontend/ reads it via SICA_ARTIFACTS_DIR.
    artifacts: str = DEFAULT_ARTIFACTS_DIR
```

In `load_ingest_config`'s `IngestConfig(...)` call, after `local_area_boundary_geojson=...`:

```python
        artifacts=str(flat.get("artifacts", DEFAULT_ARTIFACTS_DIR)),
```

In `src/sica_core/paths.py`, under `# raw/ sources`, after `block_numbers_csv`:

```python
        self.local_area_boundary_geojson = self.cov("local-area-boundary", "geojson")
```

Under `# derived/`, after `db`:

```python
        self.artifacts = self.derived / "artifacts"
```

In `config.toml` `[paths]`, after `local_area_boundary_geojson`:

```toml
artifacts = "data/derived/artifacts"
```

- [ ] **Step 4: Rewrite `scripts/rebuild_map.py`**

```python
#!/usr/bin/env python3
"""Rebuilds sica_core's SQLite store and exports the frontend artifact set.

Backend only: ingests the sources into SQLite, then writes the artifact
directory (config.toml's `artifacts` path) that frontend/ reads. It renders
nothing — see frontend/README.md for the map.

--skip-ingest  re-export from the existing database without re-ingesting
               (saves ~19s when only export logic changed). Never touches
               the database's tables.
--folium       additionally render the legacy Folium map into www/, as the
               parity reference for the Vite build. Temporary: removed with
               sica_mapping.

Usage: uv run python scripts/rebuild_map.py [--config config.toml] [--skip-ingest] [--folium]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sica_core.config import load_ingest_config  # noqa: E402
from sica_core.db import get_connection, init_db  # noqa: E402
from sica_core.export import export_artifacts, export_to_cache  # noqa: E402
from sica_core.ingest import run_ingest  # noqa: E402

# Only used by --folium: sica_mapping.cli.DEFAULT_DATA_DIR.
LEGACY_CACHE_DIR = REPO_ROOT / ".preprocessed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(REPO_ROOT / "config.toml"))
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--folium", action="store_true")
    args = parser.parse_args()

    config = load_ingest_config(args.config)
    conn = get_connection(config.db_path)
    if args.skip_ingest:
        print(f"Skipping ingest; exporting from {config.db_path}")
    else:
        print(f"Ingesting into {config.db_path} ...")
        init_db(conn)
        counts = run_ingest(conn, config)
        print(f"Ingest complete: {counts}")

    print(f"Exporting artifacts to {config.artifacts} ...")
    export_artifacts(
        conn,
        config.artifacts,
        pid_address_map_path=config.pid_address_map,
        boundary_geojson_path=config.local_area_boundary_geojson,
    )

    if args.folium:
        print("Rendering the legacy Folium map (parity reference) ...")
        export_to_cache(conn, LEGACY_CACHE_DIR, pid_address_map_path=config.pid_address_map)
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "build_sica_map.py"),
                "--config", args.config,
                "--stage", "frontend",
                "--data-dir", str(LEGACY_CACHE_DIR),
            ],
            cwd=REPO_ROOT,
            check=True,
        )
        print("Legacy map: www/index.html")

    print(f"Done — artifacts in {config.artifacts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Update the rebuild order in `data/README.md`**

Replace line 21:

```
uv run python scripts/rebuild_map.py                            # www/index.html
```

with:

```
uv run python scripts/rebuild_map.py                            # derived/artifacts (the frontend's input)
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_rebuild_map.py tests/test_data_layout.py -v`
Expected: all pass.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: 60 passed (58 + 2).

- [ ] **Step 8: Verify on real data**

```bash
uv run python scripts/rebuild_map.py --skip-ingest
ls -la data/derived/artifacts
uv run python scripts/rebuild_map.py --skip-ingest --folium
test -f www/index.html && echo "Folium reference still builds"
```

Expected: five files in `data/derived/artifacts` (`filter_config.json`, `marker_metadata.json`, `building_records.json`, `blocks.geojson`, `local-area-boundary.geojson`), and the Folium reference still builds.

- [ ] **Step 9: Commit** *(ask first)*

```bash
git add scripts/rebuild_map.py src/sica_core/config.py src/sica_core/paths.py \
        config.toml tests/test_rebuild_map.py tests/test_data_layout.py data/README.md
git commit -m "Make rebuild_map.py backend-only: ingest then export_artifacts"
```

---

### Task 2: Round coordinates in the export

Measured on real data, `blocks.geojson` is 3.68 MB gzipped, and the whole artifact set is 4.38 MB. That is no smaller than today's ~4.2 MB Folium page. The cause is coordinates carrying 15 decimals. Rounding block geometry to 6 decimals (~10 cm) brings `blocks.geojson` to 1.45 MB and the set to 2.16 MB. Rounding marker and record `lat`/`lon` too (D17) gives 2.05 MB.

This task sits here, before the frontend, so that Task 8's size check measures the real result and Task 12's fixtures are generated with it. `local-area-boundary.geojson` is left untouched: it's a passthrough of the City's file, and only 0.02 MB. No `schema_version` bump, because the shape is unchanged and only precision changes.

**Files:**
- Modify: `src/sica_core/export.py` (`_blocks_feature_collection`, `_marker_records`, `_building_records`; new `COORD_DECIMALS` and rounding helpers)
- Test: `tests/test_export_artifacts.py` (three tests added; the file's existing imports cover them)

**Interfaces:**
- Produces: `export_artifacts()` output in which every coordinate in `blocks.geojson` geometry, and every `lat`/`lon` in `marker_metadata.json` and `building_records.json`, is rounded to `COORD_DECIMALS = 6`. `local-area-boundary.geojson` stays byte-identical to its source. `filter_config.json`'s `bounds` stay unrounded (they only set the initial view).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_export_artifacts.py`:

```python
def _decimals(x: float) -> int:
    text = repr(x)
    return len(text.split(".")[1]) if "." in text else 0


def _all_floats(value):
    if isinstance(value, list):
        for v in value:
            yield from _all_floats(v)
    elif isinstance(value, float):
        yield value


def _seed_precise(conn):
    """Coordinates at the 15-decimal precision the real sources carry."""
    conn.execute(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, "
        "created_at, updated_at) VALUES ('1 a st', '1 A St', 49.283997559919406, "
        "-123.14190280987349, 'Downtown', 10, 'now', 'now')"
    )
    geom = {"type": "Polygon", "coordinates": [[
        [-123.06230338496285, 49.243279193752706],
        [-123.06204402014143, 49.243509152622245],
        [-123.0621556622, 49.2436],
        [-123.06230338496285, 49.243279193752706],
    ]]}
    conn.execute(
        "INSERT INTO blocks (block_id, geom, ingested_at) VALUES (1, ?, 'now')",
        (json.dumps(geom),),
    )
    conn.commit()


def test_block_geometry_is_rounded_to_six_decimals(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_precise(conn)

    export_artifacts(conn, tmp_path)

    geom = json.loads((tmp_path / "blocks.geojson").read_text())["features"][0]["geometry"]
    coords = list(_all_floats(geom["coordinates"]))
    assert coords and all(_decimals(c) <= 6 for c in coords)
    assert geom["coordinates"][0][0] == [-123.062303, 49.243279]


def test_marker_and_record_coordinates_are_rounded(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_precise(conn)

    export_artifacts(conn, tmp_path)

    marker = json.loads((tmp_path / "marker_metadata.json").read_text())["markers"][0]
    records = json.loads((tmp_path / "building_records.json").read_text())["records"]
    record = next(iter(records.values()))
    assert (marker["lat"], marker["lon"]) == (49.283998, -123.141903)
    assert (record["lat"], record["lon"]) == (49.283998, -123.141903)


def test_boundary_passthrough_is_byte_identical(tmp_path):
    """The City's file is copied, never rewritten — its precision included."""
    content = json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"name": "X"},
        "geometry": {"type": "Point", "coordinates": [-123.14190280987349, 49.283997559919406]},
    }]})
    src = tmp_path / "boundary.geojson"
    src.write_text(content)
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_precise(conn)

    export_artifacts(conn, tmp_path / "out", boundary_geojson_path=str(src))

    assert (tmp_path / "out" / "local-area-boundary.geojson").read_text() == content
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_export_artifacts.py -v`
Expected: the two rounding tests FAIL, showing 15-decimal values. `test_boundary_passthrough_is_byte_identical` passes immediately: it guards the "leave the passthrough alone" requirement rather than driving a change.

- [ ] **Step 3: Add the rounding helpers**

In `src/sica_core/export.py`, directly below `SCHEMA_VERSION = 1`:

```python
# ~10 cm. The sources carry 15-decimal coordinates, which made blocks.geojson
# 3.68 MB gzipped — larger than the whole Folium page it replaces. At 6
# decimals it is 1.45 MB; nothing on the map resolves finer.
COORD_DECIMALS = 6


def _round_coords(value):
    """Round every float in a (nested) GeoJSON coordinates array."""
    if isinstance(value, float):
        return round(value, COORD_DECIMALS)
    if isinstance(value, (list, tuple)):
        return [_round_coords(v) for v in value]
    return value


def _round_geometry(geom: dict) -> dict:
    if "coordinates" in geom:
        return {**geom, "coordinates": _round_coords(geom["coordinates"])}
    if "geometries" in geom:  # GeometryCollection
        return {**geom, "geometries": [_round_geometry(g) for g in geom["geometries"]]}
    return geom


def _round_coord(value) -> float | None:
    return None if value is None or pd.isna(value) else round(float(value), COORD_DECIMALS)
```

- [ ] **Step 4: Apply them**

In `_blocks_feature_collection`, change `"geometry": geom,` to:

```python
                "geometry": _round_geometry(geom),
```

In `_marker_records`, change the two coordinate entries to:

```python
                "lat": _round_coord(r["lat"]),
                "lon": _round_coord(r["lon"]),
```

and correct its docstring, which predates D3. The styling moved to the frontend:

```python
    """Per-building marker data, including coordinates.

    Styling (radius, colours, rings) is presentation and is computed by the
    frontend (frontend/src/markers.ts); these records carry only data.
    """
```

In `_building_records`, after the `rec = {...}` comprehension and before `records[...] = rec`:

```python
        for c in ("lat", "lon"):
            if c in rec:
                rec[c] = _round_coord(rec[c])
```

In `_write_json`, drop `default=str`, so a numpy value that leaks into a record raises instead of being silently stringified (the previous plan's review verified the real export holds only native types):

```python
def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_export_artifacts.py -v`
Expected: all pass, including the existing `test_marker_metadata_carries_coordinates` (49.28 is unchanged by rounding).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: 63 passed (60 + 3).

- [ ] **Step 7: Measure on real data**

```bash
uv run python scripts/rebuild_map.py --skip-ingest
python3 - <<'EOF'
import gzip
from pathlib import Path
total = 0
for f in sorted(Path("data/derived/artifacts").iterdir()):
    n = len(gzip.compress(f.read_bytes(), 6))
    total += n
    print(f"{f.name:32} {n / 1e6:5.2f} MB gz")
print(f"{'total':32} {total / 1e6:5.2f} MB gz")
EOF
```

Expected: `blocks.geojson` about 1.45 MB and the total about 2.05 MB (measured during planning; the exact figure moves with the data). Record both in the task report.

- [ ] **Step 8: Commit** *(ask first)*

```bash
git add src/sica_core/export.py tests/test_export_artifacts.py
git commit -m "Round exported coordinates to 6 decimals (~10 cm)"
```

---

### Task 3: Scaffold `frontend/` with the artifact-directory plugin

Spec §6: a Vite + TS project whose only input is the artifact directory, found through `SICA_ARTIFACTS_DIR`, served at `/data/` in dev and copied to `dist/data/` on build.

**Files:**
- Create: `frontend/package.json`, `frontend/.nvmrc`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/artifacts-plugin.ts`, `frontend/README.md`
- Create: `frontend/package-lock.json` (generated by npm)
- Modify: `.gitignore`
- Test: `frontend/artifacts-plugin.test.ts`

**Interfaces:**
- Produces: `resolveArtifactPath(dir: string, url: string): string | null` and `sicaArtifacts(dir: string): Plugin`, both from `frontend/artifacts-plugin.ts`. npm scripts `dev`, `build`, `preview`, `typecheck` and `test`.

- [ ] **Step 1: Create the project files**

`frontend/.nvmrc`:

```
24
```

`frontend/package.json` (npm fills in the dependency sections in Step 2):

```json
{
  "name": "sica-map",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "engines": { "node": ">=24" },
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  }
}
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["vite/client", "node"],
    "strict": true,
    "allowJs": true,
    "checkJs": false,
    "noEmit": true,
    "isolatedModules": true,
    "skipLibCheck": true
  },
  "include": ["src", "vite.config.ts", "artifacts-plugin.ts", "artifacts-plugin.test.ts"]
}
```

Append to the repo-root `.gitignore`:

```
# frontend/ build output and dependencies (frontend/fixtures/ IS committed)
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 2: Install dependencies**

```bash
cd frontend
npm install --save-exact leaflet@1.9.3 bootstrap@5.2.2
npm install --save-dev vite typescript vitest @types/leaflet @types/geojson @types/node
```

This writes `package-lock.json`, which pins every version. `@types/geojson` is listed explicitly because `src/types.ts` imports from it; otherwise it would only resolve indirectly, through `@types/leaflet`. `bootstrap` pulls in `@popperjs/core` as a peer dependency. It's unused (only Bootstrap's reboot CSS is imported) and harmless.

- [ ] **Step 3: Write the failing test**

```ts
// frontend/artifacts-plugin.test.ts
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { resolveArtifactPath } from './artifacts-plugin';

const DIR = resolve('/srv/artifacts');

describe('resolveArtifactPath', () => {
  it('maps a request path into the artifact directory', () => {
    expect(resolveArtifactPath(DIR, '/marker_metadata.json')).toBe(resolve(DIR, 'marker_metadata.json'));
  });

  it('ignores the query string', () => {
    expect(resolveArtifactPath(DIR, '/blocks.geojson?v=2')).toBe(resolve(DIR, 'blocks.geojson'));
  });

  it('refuses to escape the directory', () => {
    expect(resolveArtifactPath(DIR, '/../secret.json')).toBeNull();
    expect(resolveArtifactPath(DIR, '/%2e%2e/secret.json')).toBeNull();
  });

  it('refuses the directory itself', () => {
    expect(resolveArtifactPath(DIR, '/')).toBeNull();
  });

  it('returns null for malformed percent-encoding instead of throwing', () => {
    expect(resolveArtifactPath(DIR, '/%E0')).toBeNull();
  });
});
```

- [ ] **Step 4: Run it to verify it fails**

Run: `npm test`
Expected: FAIL, `Failed to resolve import "./artifacts-plugin"`.

- [ ] **Step 5: Write the plugin and the Vite config**

`frontend/artifacts-plugin.ts`:

```ts
/**
 * The artifact directory is the frontend's only input (spec §3). Under
 * `npm run dev` it is served at /data/; `npm run build` copies it into
 * dist/data/. Which directory is a single setting, SICA_ARTIFACTS_DIR,
 * resolved in vite.config.ts.
 */
import { cpSync, createReadStream, existsSync, statSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import type { Plugin } from 'vite';

/** Absolute path for a /data/ request, or null if it escapes `dir`, names `dir` itself, or is malformed. */
export function resolveArtifactPath(dir: string, url: string): string | null {
  let rel: string;
  try {
    rel = decodeURIComponent(url.split('?')[0]);
  } catch {
    return null; // malformed percent-encoding, e.g. /%E0 (decodeURIComponent throws URIError)
  }
  const file = resolve(dir, '.' + rel);
  return file.startsWith(dir + sep) ? file : null;
}

function requireDir(dir: string): void {
  if (!existsSync(dir) || !statSync(dir).isDirectory()) {
    throw new Error(
      `Artifact directory not found: ${dir}\n` +
        'Run `uv run python scripts/rebuild_map.py` from the repo root, ' +
        'or point SICA_ARTIFACTS_DIR at an artifact directory (e.g. SICA_ARTIFACTS_DIR=fixtures).',
    );
  }
}

export function sicaArtifacts(dir: string): Plugin {
  let outDir = '';
  let command: 'build' | 'serve' = 'serve';
  return {
    name: 'sica-artifacts',
    configResolved(config) {
      command = config.command;
      outDir = resolve(config.root, config.build.outDir);
    },
    buildStart() {
      // Only a build needs the directory. Vite's dev server (which Vitest
      // also runs) calls buildStart too, and tests must not depend on it.
      if (command === 'build') requireDir(dir);
    },
    configureServer(server) {
      if (!process.env.VITEST && !existsSync(dir)) {
        server.config.logger.warn(
          `Artifact directory not found: ${dir} — the map will show a load error. ` +
            'Run `uv run python scripts/rebuild_map.py` from the repo root, or set SICA_ARTIFACTS_DIR.',
        );
      }
      server.middlewares.use('/data', (req, res, next) => {
        const file = resolveArtifactPath(dir, req.url ?? '/');
        if (!file || !existsSync(file) || !statSync(file).isFile()) return next();
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        createReadStream(file).pipe(res);
      });
    },
    writeBundle() {
      cpSync(dir, resolve(outDir, 'data'), { recursive: true });
    },
  };
}
```

`frontend/vite.config.ts`:

```ts
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import { sicaArtifacts } from './artifacts-plugin';

const HERE = fileURLToPath(new URL('.', import.meta.url));
// Relative values resolve against the current directory (frontend/ under npm).
const ARTIFACTS_DIR = resolve(
  process.env.SICA_ARTIFACTS_DIR ?? resolve(HERE, '../data/derived/artifacts'),
);

export default defineConfig({
  // Relative asset and artifact URLs, so dist/ works from any path (e.g. a Pages subpath).
  base: './',
  plugins: [sicaArtifacts(ARTIFACTS_DIR)],
  test: { environment: 'node' },
});
```

- [ ] **Step 6: Write `frontend/README.md`**

````markdown
# SICA map frontend

A Vite + TypeScript project that renders the map from `sica_core`'s artifact
directory. It reads nothing else: no CSV, no SQLite, no Python.

## Toolchains

Only this half needs Node (version in `.nvmrc`, currently 24 LTS). The backend
(`sica_core`, `uv`) is only needed to *produce* artifacts; a checkout can build
the frontend against `fixtures/` with Node alone.

## Artifacts

`SICA_ARTIFACTS_DIR` names the artifact directory (default
`../data/derived/artifacts`, produced by `uv run python scripts/rebuild_map.py`
from the repo root). It is served at `/data/` by `npm run dev` and copied into
`dist/data/` by `npm run build`. Contract: `filter_config.json`,
`marker_metadata.json`, `building_records.json` and `blocks.geojson` each carry
`schema_version` (checked at load); `local-area-boundary.geojson` is the City's
file, passed through.

## Commands

```bash
npm ci                                      # install (pinned by package-lock.json)
npm run dev                                 # dev server with hot reload
npm run build                               # dist/, including dist/data/
SICA_ARTIFACTS_DIR=fixtures npm run build   # build against the synthetic fixtures
npm run preview                             # serve dist/
npm test                                    # unit tests (Vitest)
npm run typecheck                           # tsc --noEmit
```
````

The `fixtures/` line refers to Task 12. Its commands fail with the plugin's "Artifact directory not found" message until then.

- [ ] **Step 7: Run tests and the type check**

Run: `npm test && npm run typecheck`
Expected: 5 passed; `tsc` reports nothing.

- [ ] **Step 8: Commit** *(ask first)*

```bash
cd ..
git add .gitignore frontend/package.json frontend/package-lock.json frontend/.nvmrc \
        frontend/tsconfig.json frontend/vite.config.ts frontend/artifacts-plugin.ts \
        frontend/artifacts-plugin.test.ts frontend/README.md
git commit -m "Scaffold the frontend/ Vite project and its artifact-directory plugin"
```

---

### Task 4: `index.html`, config, artifact types and schema-checked loading

`index.html` is assembled from the three HTML fragments verbatim, including their `<style>` blocks. Placeholders are replaced by empty containers, which later tasks fill from the DOM.

**Files:**
- Create: `frontend/index.html` (generated once in Step 1)
- Create: `frontend/src/config.ts`, `frontend/src/types.ts`, `frontend/src/data.ts`
- Test: `frontend/src/data.test.ts`

**Interfaces:**
- Consumes: `src/sica_mapping/frontend/templates/{sidebar,legend_blocks,legend_filters}.html` (read only).
- Produces:
  - `config.ts`: `SIDEBAR_WIDTH = 540`, `LEGEND_LEFT_OFFSET = 560`, `EXPECTED_SCHEMA_VERSION = 1`, `artifactUrl(name: string): string`, `BASEMAPS`, `DEFAULT_BASEMAP`, `DEFAULT_CENTER`, `DEFAULT_ZOOM`.
  - `types.ts`: `MarkerRecord`, `FilterConfig`, `NeighbourhoodSummary`, `BuildingRecord`, `BuildingData`, `BlockProperties`, `BlocksCollection`, `BoundaryProperties`, `BoundaryCollection`, `Artifacts`.
  - `data.ts`: `class ArtifactError extends Error`, `checkSchemaVersion(name: string, payload: unknown): void`, `loadArtifacts(): Promise<Artifacts>`.

- [ ] **Step 1: Generate `index.html` from the fragments**

Run from the repo root. The asserts guard against any placeholder surviving:

```bash
uv run python - <<'EOF'
import re
from pathlib import Path

T = Path("src/sica_mapping/frontend/templates")


def take(name, replacements):
    s = (T / name).read_text()
    for old, new in replacements:
        assert s.count(old) == 1, (name, old)
        s = s.replace(old, new)
    return s.strip("\n")


sidebar = take("sidebar.html", [
    ("<tbody>$neighbourhoods_rows</tbody>", "<tbody></tbody>"),
    ("<tbody>$blocks_rows</tbody>", "<tbody></tbody>"),
    ("<tbody>$buildings_rows</tbody>", "<tbody></tbody>"),
    ("<tbody>$landlords_rows</tbody>", "<tbody></tbody>"),
])
legend_blocks = take("legend_blocks.html", [
    ('style="left:${legend_left_offset}px; display:none;"', 'style="display:none;"'),
    ("      $block_ticks_html\n", ""),
    ("Color scaled to 0–$block_max_label units (visible blocks).", ""),
])
legend_filters = take("legend_filters.html", [
    ("        $hood_html\n", ""),
])

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>SICA Map</title>
<style>
  /* Page and map container: the rules Folium put in <head>. */
  html, body {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
  #map {{ position: absolute; top: 0; bottom: 0; right: 0; left: 0; }}
  .leaflet-container {{ font-size: 1rem; }}
  #load-error {{
    position: fixed; top: 12px; left: 50%; transform: translateX(-50%); z-index: 10000;
    max-width: 80vw; padding: 8px 14px; border-radius: 4px;
    background: #b00020; color: #fff; font: 14px/1.4 system-ui, sans-serif;
  }}
</style>
</head>
<body>
<div id="map"></div>
<!-- from sica_mapping/frontend/templates/sidebar.html -->
{sidebar}
<!-- from sica_mapping/frontend/templates/legend_blocks.html -->
{legend_blocks}
<!-- from sica_mapping/frontend/templates/legend_filters.html -->
{legend_filters}
<script type="module" src="/src/bootstrap.ts"></script>
</body>
</html>
"""
leftover = re.findall(r"\$[{A-Za-z_]", page)
assert not leftover, leftover
Path("frontend/index.html").write_text(page)
print("wrote frontend/index.html")
EOF
```

DOM order matches the Folium page: map, sidebar, block legend, filters panel. `/src/bootstrap.ts` is written in Task 8. Until then `npm run dev` shows the unstyled page with a 404 for the script, which is expected.

- [ ] **Step 2: Verify every id `wiring.js` needs is present**

```bash
uv run python - <<'EOF'
import re
from pathlib import Path
page = Path("frontend/index.html").read_text()
wiring = Path("src/sica_mapping/frontend/templates/wiring.js").read_text()
need = set(re.findall(r"getElementById\('([^']+)'\)", wiring)) | set(re.findall(r"'(summary-[a-z]+-[a-z]+)'", wiring)) | set(re.findall(r"'#([a-z-]+) ", wiring))
have = set(re.findall(r'''id=['"]([^'"]+)['"]''', page))
missing = sorted(need - have)
assert not missing, missing
print(f"all {len(need)} ids present")
EOF
```

Expected: `all 61 ids present`.

- [ ] **Step 3: Write the failing test**

```ts
// frontend/src/data.test.ts
import { describe, expect, it } from 'vitest';
import { ArtifactError, checkSchemaVersion } from './data';

describe('checkSchemaVersion', () => {
  it('accepts the expected version', () => {
    expect(() => checkSchemaVersion('marker_metadata.json', { schema_version: 1, markers: [] })).not.toThrow();
  });

  it('rejects a different version, naming the file', () => {
    expect(() => checkSchemaVersion('blocks.geojson', { schema_version: 2 })).toThrow(ArtifactError);
    expect(() => checkSchemaVersion('blocks.geojson', { schema_version: 2 })).toThrow(/blocks\.geojson/);
  });

  it('rejects a payload with no version (e.g. a pre-contract file)', () => {
    expect(() => checkSchemaVersion('filter_config.json', {})).toThrow(ArtifactError);
    expect(() => checkSchemaVersion('filter_config.json', [])).toThrow(ArtifactError);
  });
});
```

- [ ] **Step 4: Run it to verify it fails**

Run: `npm test`
Expected: FAIL, `Failed to resolve import "./data"`.

- [ ] **Step 5: Write `config.ts`, `types.ts` and `data.ts`**

`frontend/src/config.ts`:

```ts
/** Presentation settings, formerly config.toml's [options] and build.py's tile presets. */

/** config.toml's former [options].sidebar_width. */
export const SIDEBAR_WIDTH = 540;
/** legends_html(): the block legend sits just right of the sidebar. */
export const LEGEND_LEFT_OFFSET = SIDEBAR_WIDTH + 20;

/** The artifact contract version this frontend understands (spec §4). */
export const EXPECTED_SCHEMA_VERSION = 1;

/** Artifact files live at <base>/data/ (served or copied by artifacts-plugin.ts). */
export function artifactUrl(name: string): string {
  return `${import.meta.env.BASE_URL}data/${name}`;
}

export interface Basemap {
  tiles: string;
  attribution: string;
  /** Optional reference layer (street/place labels) drawn above the base tiles. */
  labels?: string;
}

// Keyless Esri Light Gray Canvas. CARTO retired unauthenticated access to its
// positron tiles; this is the closest drop-in that needs no key.
const ESRI_CANVAS = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas';
const ESRI_GRAY_ATTR = 'Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors';

export const BASEMAPS: Record<string, Basemap> = {
  'esri-gray': {
    tiles: `${ESRI_CANVAS}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    attribution: ESRI_GRAY_ATTR,
    labels: `${ESRI_CANVAS}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
  },
  'esri-gray-plain': {
    tiles: `${ESRI_CANVAS}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    attribution: ESRI_GRAY_ATTR,
  },
};

/** config.toml's former [options].tiles. */
export const DEFAULT_BASEMAP = 'esri-gray';
/** Only used if filter_config.json has no bounds; build.py's fallback. */
export const DEFAULT_CENTER: [number, number] = [49.286, -123.135];
export const DEFAULT_ZOOM = 14;
```

`frontend/src/types.ts`:

```ts
/** Shapes of the artifact files (spec §4). Fields the frontend does not read are omitted. */
import type { FeatureCollection, Geometry } from 'geojson';

export interface MarkerRecord {
  b_id: number;
  lat: number | null;
  lon: number | null;
  owner_key: string | null;
  block_id: number | null;
  units: number | null;
  year_built: number | null;
  local_area: string | null;
  is_vtu: boolean;
  member_count: number;
  /** "co-op, sro" | "co-op" | "sro" | "" */
  housing_type: string;
  /** "building" | "overlay_sro" | "overlay_coop" */
  source: string;
}

export interface NeighbourhoodSummary {
  name: string;
  count: number;
  units: number;
}

export interface FilterConfig {
  schema_version: number;
  bounds?: { lat_min: number; lat_max: number; lon_min: number; lon_max: number } | null;
  neighbourhoods?: NeighbourhoodSummary[];
  blocks_total_units_max?: number | null;
  blocks_member_building_max?: number | null;
  [key: string]: unknown;
}

/**
 * One row of building_records.json: the 41 columns of sica_core's
 * export.BUILDING_RECORD_COLUMNS, read defensively. Overlay text fields are ''
 * on building rows and null on overlay rows; treat both as empty.
 */
export type BuildingRecord = { b_id: number } & Record<string, unknown>;

export interface BuildingData {
  schema_version: number;
  columns: string[];
  records: Record<string, BuildingRecord>;
}

export interface BlockProperties {
  block_id: number;
  block_label: string | null;
  local_area: string | null;
  buildings: number | null;
  total_units: number | null;
  median_year_built: number | null;
  member_buildings: number | null;
  total_members: number | null;
  member_share: number | null;
}

export type BlocksCollection = FeatureCollection<Geometry, BlockProperties> & { schema_version: number };

export interface BoundaryProperties {
  name?: string;
  /** The City's representative point for the area, when present. */
  geo_point_2d?: { lat: number; lon: number };
}

export type BoundaryCollection = FeatureCollection<Geometry, BoundaryProperties>;

export interface Artifacts {
  filterConfig: FilterConfig;
  markers: MarkerRecord[];
  buildingData: BuildingData;
  blocks: BlocksCollection;
  boundaries: BoundaryCollection;
}
```

`frontend/src/data.ts`:

```ts
/** Loads the artifact directory once and checks its contract version (spec §4). */
import { EXPECTED_SCHEMA_VERSION, artifactUrl } from './config';
import type { Artifacts, BlocksCollection, BoundaryCollection, BuildingData, FilterConfig, MarkerRecord } from './types';

export class ArtifactError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ArtifactError';
  }
}

/** Throws unless `payload.schema_version` is the version this frontend understands. */
export function checkSchemaVersion(name: string, payload: unknown): void {
  const version =
    payload && typeof payload === 'object' ? (payload as { schema_version?: unknown }).schema_version : undefined;
  if (version !== EXPECTED_SCHEMA_VERSION) {
    throw new ArtifactError(
      `${name}: expected schema_version ${EXPECTED_SCHEMA_VERSION}, got ${JSON.stringify(version)}. ` +
        'Rebuild the artifacts (uv run python scripts/rebuild_map.py) or update the frontend.',
    );
  }
}

async function fetchJson(name: string): Promise<unknown> {
  const url = artifactUrl(name);
  const resp = await fetch(url, { cache: 'no-cache' });
  if (!resp.ok) throw new ArtifactError(`${name}: HTTP ${resp.status} from ${url}`);
  return resp.json();
}

export async function loadArtifacts(): Promise<Artifacts> {
  const [filterConfig, markerMetadata, buildingData, blocks, boundaries] = await Promise.all([
    fetchJson('filter_config.json'),
    fetchJson('marker_metadata.json'),
    fetchJson('building_records.json'),
    fetchJson('blocks.geojson'),
    fetchJson('local-area-boundary.geojson'),
  ]);
  checkSchemaVersion('filter_config.json', filterConfig);
  checkSchemaVersion('marker_metadata.json', markerMetadata);
  checkSchemaVersion('building_records.json', buildingData);
  checkSchemaVersion('blocks.geojson', blocks);
  // local-area-boundary.geojson is the City's file passed through unchanged;
  // it has no schema_version by design.
  return {
    filterConfig: filterConfig as FilterConfig,
    markers: (markerMetadata as { markers: MarkerRecord[] }).markers,
    buildingData: buildingData as BuildingData,
    blocks: blocks as BlocksCollection,
    boundaries: boundaries as BoundaryCollection,
  };
}
```

- [ ] **Step 6: Run tests and the type check**

Run: `npm test && npm run typecheck`
Expected: 8 passed (5 + 3); `tsc` reports nothing.

- [ ] **Step 7: Commit** *(ask first)*

```bash
git add frontend/index.html frontend/src/config.ts frontend/src/types.ts \
        frontend/src/data.ts frontend/src/data.test.ts
git commit -m "Add the frontend page shell, presentation config and schema-checked artifact loading"
```

---

### Task 5: Marker styling (`markers.ts`)

Per D3. This ports `layout.py`'s `marker_radius()`, the VTU fill colours and the housing-type ring logic from `add_buildings_layers()` (`layout.py:138-316`). The output fields are exactly what `wiring.js`'s `applyMarkerMetadata()` reads.

**Files:**
- Create: `frontend/src/markers.ts`
- Test: `frontend/src/markers.test.ts`

**Interfaces:**
- Consumes: `MarkerRecord` (Task 4).
- Produces: `markerRadius(units: number | null | undefined): number`; `type HousingType = 'coop' | 'sro'`; `housingTypes(housingType: string): HousingType[]`; `ringColor(t: HousingType): string`; `interface MarkerStyle { base_color: string; neutral_color: string; base_opacity: number; base_radius: number; stroke_color: string; stroke_weight: number; primary_housing_type: HousingType | ''; extra_rings: { housing_type: HousingType }[] }`; `markerStyle(r: MarkerRecord): MarkerStyle`; `type StyledMarker = MarkerRecord & MarkerStyle`. Also the constants `RING_WEIGHT = 2.0`, `RING_OPACITY = 0.9`, `RING_SPACING = 3.0`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/markers.test.ts
import { describe, expect, it } from 'vitest';
import { housingTypes, markerRadius, markerStyle } from './markers';
import type { MarkerRecord } from './types';

const base: MarkerRecord = {
  b_id: 1, lat: 49.28, lon: -123.1, owner_key: 'x', block_id: 1, units: 40, year_built: 1970,
  local_area: 'West End', is_vtu: false, member_count: 0, housing_type: '', source: 'building',
};

describe('markerRadius', () => {
  it('matches layout.py for a real building (449 units)', () => {
    // From the Folium-era marker metadata: base_radius 9.18345683964709.
    expect(markerRadius(449)).toBeCloseTo(9.18345683964709, 12);
  });

  it('caps at 600 units and floors missing or non-positive values at 3.2', () => {
    expect(markerRadius(600)).toBeCloseTo(9.5, 12);
    expect(markerRadius(5000)).toBeCloseTo(9.5, 12);
    expect(markerRadius(null)).toBe(3.2);
    expect(markerRadius(0)).toBe(3.2);
    expect(markerRadius(Number.NaN)).toBe(3.2);
  });
});

describe('housingTypes', () => {
  it('orders co-op before SRO, as layout.py did', () => {
    expect(housingTypes('co-op, sro')).toEqual(['coop', 'sro']);
    expect(housingTypes('sro')).toEqual(['sro']);
    expect(housingTypes('')).toEqual([]);
  });
});

describe('markerStyle', () => {
  it('colours VTU buildings pink at 0.75 and others grey at 0.35', () => {
    expect(markerStyle({ ...base, is_vtu: true })).toMatchObject({ base_color: '#cc4778', base_opacity: 0.75 });
    expect(markerStyle(base)).toMatchObject({ base_color: '#9e9e9e', base_opacity: 0.35, neutral_color: '#9e9e9e' });
  });

  it('gives a single-type building that type\'s ring as its own stroke', () => {
    expect(markerStyle({ ...base, housing_type: 'sro' })).toMatchObject({
      stroke_color: '#3182bd', stroke_weight: 2.2, primary_housing_type: 'sro', extra_rings: [],
    });
  });

  it('gives a dual building the co-op stroke plus one extra SRO ring', () => {
    expect(markerStyle({ ...base, housing_type: 'co-op, sro' })).toMatchObject({
      stroke_color: '#d97706', primary_housing_type: 'coop', extra_rings: [{ housing_type: 'sro' }],
    });
  });

  it('uses the thin white default stroke otherwise', () => {
    expect(markerStyle(base)).toMatchObject({
      stroke_color: '#ffffff', stroke_weight: 0.6, primary_housing_type: '', extra_rings: [],
    });
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm test`
Expected: FAIL, `Failed to resolve import "./markers"`.

- [ ] **Step 3: Write `markers.ts`**

```ts
/**
 * Marker styling, ported from sica_mapping/frontend/layout.py
 * (marker_radius, add_buildings_layers). Presentation, so it lives here: the
 * artifacts carry the data (units, is_vtu, housing_type), not the styling.
 * Field names match what wiring.js's applyMarkerMetadata() reads.
 */
import type { MarkerRecord } from './types';

const VTU_COLOR = '#cc4778';
const NEUTRAL_COLOR = '#9e9e9e';
const COOP_RING_COLOR = '#d97706';
const SRO_RING_COLOR = '#3182bd';
const RING_STROKE_WEIGHT = 2.2;
const DEFAULT_STROKE_COLOR = '#ffffff';
const DEFAULT_STROKE_WEIGHT = 0.6;

/** Extra rings (dual-type buildings): each one this much wider than the last. */
export const RING_SPACING = 3.0;
export const RING_WEIGHT = 2.0;
export const RING_OPACITY = 0.9;

export type HousingType = 'coop' | 'sro';

export interface MarkerStyle {
  base_color: string;
  neutral_color: string;
  base_opacity: number;
  base_radius: number;
  stroke_color: string;
  stroke_weight: number;
  primary_housing_type: HousingType | '';
  extra_rings: { housing_type: HousingType }[];
}

export type StyledMarker = MarkerRecord & MarkerStyle;

/** Log-scaled by units, capped at 600; 3.2 for missing or non-positive values. */
export function markerRadius(units: number | null | undefined): number {
  if (units === null || units === undefined || !Number.isFinite(units) || units <= 0) return 3.2;
  const capped = Math.min(Math.max(units, 1), 600);
  return 2.5 + 7.0 * (Math.log1p(capped) / Math.log1p(600));
}

/** "co-op, sro" -> ['coop', 'sro']. Co-op first: the first type owns the stroke. */
export function housingTypes(housingType: string): HousingType[] {
  const parts = housingType.split(',').map((p) => p.trim());
  const types: HousingType[] = [];
  if (parts.includes('co-op')) types.push('coop');
  if (parts.includes('sro')) types.push('sro');
  return types;
}

export function ringColor(t: HousingType): string {
  return t === 'coop' ? COOP_RING_COLOR : SRO_RING_COLOR;
}

export function markerStyle(r: MarkerRecord): MarkerStyle {
  const types = housingTypes(r.housing_type ?? '');
  return {
    base_color: r.is_vtu ? VTU_COLOR : NEUTRAL_COLOR,
    neutral_color: NEUTRAL_COLOR,
    base_opacity: r.is_vtu ? 0.75 : 0.35,
    base_radius: markerRadius(r.units),
    stroke_color: types.length ? ringColor(types[0]) : DEFAULT_STROKE_COLOR,
    stroke_weight: types.length ? RING_STROKE_WEIGHT : DEFAULT_STROKE_WEIGHT,
    primary_housing_type: types[0] ?? '',
    extra_rings: types.slice(1).map((t) => ({ housing_type: t })),
  };
}
```

- [ ] **Step 4: Run tests and the type check**

Run: `npm test && npm run typecheck`
Expected: 15 passed (8 + 7); `tsc` reports nothing.

- [ ] **Step 5: Commit** *(ask first)*

```bash
git add frontend/src/markers.ts frontend/src/markers.test.ts
git commit -m "Port marker styling from layout.py to markers.ts"
```

---

### Task 6: Block choropleth, block popup, neighbourhood labels and legend

Spec §6's three presentation pieces (block style, neighbourhood filter tags, block legend ticks), plus D9's block popup and neighbourhood labels. These are pure functions. The Leaflet construction happens in `layers.ts` in Task 8.

**Files:**
- Create: `frontend/src/html.ts` (escape + number helpers, shared by Tasks 6, 7 and 9)
- Create: `frontend/src/blocks.ts`, `frontend/src/neighbourhoods.ts`, `frontend/src/legend.ts`
- Test: `frontend/src/html.test.ts`, `frontend/src/blocks.test.ts`, `frontend/src/neighbourhoods.test.ts`, `frontend/src/legend.test.ts`

**Interfaces:**
- Produces:
  - `html.ts`: `escapeHtml(value: unknown): string` (Python's `html.escape(s, quote=True)`), `roundHalfEven(value: number, decimals?: number): number` (Python's `round()`), `groupThousands(n: number): string` (Python's `format(n, ",")`), `isMissing(v: unknown): boolean`.
  - `blocks.ts`: `greensColor(s: number | null | undefined): string`, `maxTotalUnits(fc: BlocksCollection): number`, `blockStyle(props: Partial<BlockProperties> | undefined, maxUnits: number): PathOptions`, `blockPopupHtml(props: Partial<BlockProperties>): string`.
  - `neighbourhoods.ts`: `NEIGHBOURHOOD_STYLE: PathOptions`, `neighbourhoodLabelHtml(name: string): string`, `labelPosition(props: BoundaryProperties | null | undefined, fallback: [number, number]): [number, number]`.
  - `legend.ts`: `hoodTagsHtml(hoods: NeighbourhoodSummary[] | undefined): string`, `blockLegendMax(fc: FilterConfig): number`, `blockTicks(max: number): string[]`, `renderLegend(fc: FilterConfig, doc?: Document): void`.

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/src/html.test.ts
import { describe, expect, it } from 'vitest';
import { escapeHtml, groupThousands, isMissing, roundHalfEven } from './html';

describe('escapeHtml', () => {
  it("matches Python's html.escape(quote=True)", () => {
    expect(escapeHtml(`<a href="x">&'`)).toBe('&lt;a href=&quot;x&quot;&gt;&amp;&#x27;');
    expect(escapeHtml(null)).toBe('');
  });
});

describe('roundHalfEven', () => {
  it("rounds halves to even, like Python's round()", () => {
    expect(roundHalfEven(12.5)).toBe(12);
    expect(roundHalfEven(13.5)).toBe(14);
    expect(roundHalfEven(-2.5)).toBe(-2);
    expect(roundHalfEven(1.25, 1)).toBe(1.2);
    expect(roundHalfEven(2.675, 2)).toBe(2.67); // binary 2.67499…, as in Python
    expect(roundHalfEven(12.6)).toBe(13);
  });
});

describe('groupThousands / isMissing', () => {
  it('groups en-US style regardless of locale', () => {
    expect(groupThousands(1234567)).toBe('1,234,567');
  });
  it('treats null, undefined and NaN as missing, but not 0 or ""', () => {
    expect([null, undefined, Number.NaN].every(isMissing)).toBe(true);
    expect(isMissing(0) || isMissing('')).toBe(false);
  });
});
```

```ts
// frontend/src/blocks.test.ts
import { describe, expect, it } from 'vitest';
import { blockPopupHtml, blockStyle, greensColor, maxTotalUnits } from './blocks';
import type { BlocksCollection } from './types';

describe('greensColor', () => {
  it('matches colors.py greens_color at each threshold', () => {
    expect([0, 0.1, 0.2, 0.5, 0.75, 0.99, 1, 2, null].map(greensColor)).toEqual([
      '#c7e9c0', '#c7e9c0', '#a1d99b', '#74c476', '#41ab5d', '#238b45', '#005a32', '#005a32', '#c7e9c0',
    ]);
  });
});

describe('blockStyle', () => {
  it('leaves empty blocks transparent', () => {
    expect(blockStyle({ buildings: 0, total_units: 0 }, 100)).toEqual({
      fillColor: 'transparent', color: '#b8b8b8', weight: 1, fillOpacity: 0,
    });
  });
  it('scales units against the dataset maximum', () => {
    expect(blockStyle({ buildings: 3, total_units: 50 }, 100)).toEqual({
      fillColor: '#74c476', color: '#b8b8b8', weight: 1, fillOpacity: 0.7,
    });
  });
});

describe('maxTotalUnits', () => {
  it('takes the largest total_units, truncated like int()', () => {
    const fc = { type: 'FeatureCollection', schema_version: 1, features: [
      { type: 'Feature', geometry: null, properties: { total_units: 12.9 } },
      { type: 'Feature', geometry: null, properties: { total_units: null } },
    ] } as unknown as BlocksCollection;
    expect(maxTotalUnits(fc)).toBe(12);
  });
});

describe('blockPopupHtml', () => {
  it('lists the six Folium popup fields in order, escaping text and not grouping the year', () => {
    const html = blockPopupHtml({
      block_label: 'West <End>-03', buildings: 12, total_units: 1234, median_year_built: 1965.4,
      member_buildings: 2, total_members: 3,
    });
    const aliases = [...html.matchAll(/<th>([^<]*)<\/th>/g)].map((m) => m[1]);
    expect(aliases).toEqual(['Block', 'Buildings', '# Units', 'Median year', 'Buildings w/ VTU', 'Total VTU members']);
    expect(html).toContain('West &lt;End&gt;-03');
    expect(html).toContain('<td>1965</td>');
    expect(html).toContain('<td>1,234</td>'); // en-US grouping whatever the locale
  });
});
```

```ts
// frontend/src/neighbourhoods.test.ts
import { describe, expect, it } from 'vitest';
import { labelPosition, neighbourhoodLabelHtml } from './neighbourhoods';

describe('neighbourhood labels', () => {
  it('escapes the name inside the orange label', () => {
    const html = neighbourhoodLabelHtml('Grandview & <Woodland>');
    expect(html).toContain('Grandview &amp; &lt;Woodland&gt;');
    expect(html).toContain('color:#ff8c00');
  });
  it("uses the City's geo_point_2d, falling back to the given point", () => {
    expect(labelPosition({ geo_point_2d: { lat: 49.2, lon: -123.1 } }, [0, 0])).toEqual([49.2, -123.1]);
    expect(labelPosition({ name: 'X' }, [49.3, -123.2])).toEqual([49.3, -123.2]);
  });
});
```

```ts
// frontend/src/legend.test.ts
import { describe, expect, it } from 'vitest';
import { blockLegendMax, blockTicks, hoodTagsHtml } from './legend';

describe('hoodTagsHtml', () => {
  it('renders one checked filter tag per neighbourhood, as legends_html did', () => {
    expect(hoodTagsHtml([{ name: 'West End', count: 1234, units: 56789 }])).toBe(
      '<label class="filter-tag"><input type="checkbox" class="filter-neighbourhood-option" ' +
        'value="west end" checked> West End ' +
        '<span class="filter-tag-count">(1,234 bldgs · 56,789 units)</span></label>',
    );
  });
  it('says so when there is no neighbourhood data', () => {
    expect(hoodTagsHtml([])).toBe('<em class="filter-none">No neighbourhood data</em>');
  });
});

describe('block legend', () => {
  it('draws six ticks from 0 to the maximum', () => {
    expect(blockTicks(1000)).toEqual(['0', '200', '400', '600', '800', '1,000']);
    expect(blockTicks(7)).toEqual(['0', '1', '3', '4', '6', '7']);
    expect(blockTicks(0)).toEqual(['0', '0', '0', '0', '0', '0']);
  });
  it('falls back to blocks_member_building_max, and to 0', () => {
    expect(blockLegendMax({ schema_version: 1, blocks_total_units_max: 480 })).toBe(480);
    expect(blockLegendMax({ schema_version: 1, blocks_member_building_max: 9 })).toBe(9);
    expect(blockLegendMax({ schema_version: 1 })).toBe(0);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm test`
Expected: FAIL, with unresolved imports for `./html`, `./blocks`, `./neighbourhoods` and `./legend`.

- [ ] **Step 3: Write `html.ts`**

```ts
/** String helpers matching the Python the Folium build used, so ported markup is byte-compatible. */

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;' };

/** Python's html.escape(s, quote=True). null/undefined become "". */
export function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

/**
 * Python's round() (and pandas' .round()): exact halves go to the even
 * neighbour. Like Python, it works on the binary value, so 2.675 -> 2.67.
 */
export function roundHalfEven(value: number, decimals = 0): number {
  const factor = 10 ** decimals;
  const scaled = value * factor;
  const floor = Math.floor(scaled);
  const rounded = scaled - floor === 0.5 ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(scaled);
  return rounded / factor;
}

/** Python's format(n, ","): en-US grouping whatever the browser locale. */
export function groupThousands(n: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(n);
}

/** null, undefined or NaN — pandas' notion of missing. */
export function isMissing(v: unknown): boolean {
  return v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v));
}
```

- [ ] **Step 4: Write `blocks.ts`**

```ts
/**
 * Block choropleth and popup, ported from layout.py (add_blocks_layer) and
 * colors.py (greens_color). This is the initial paint only: wiring.js's
 * recomputeBlockColorScale() repaints every block against the visible
 * blocks' own range as soon as it starts.
 */
import type { PathOptions } from 'leaflet';
import { escapeHtml, groupThousands, isMissing } from './html';
import type { BlockProperties, BlocksCollection } from './types';

export function greensColor(s: number | null | undefined): string {
  const v = s === null || s === undefined ? 0 : Math.max(0, Math.min(Number(s), 1));
  if (v <= 0.1) return '#c7e9c0';
  if (v <= 0.25) return '#a1d99b';
  if (v <= 0.5) return '#74c476';
  if (v <= 0.75) return '#41ab5d';
  if (v < 1.0) return '#238b45';
  return '#005a32';
}

export function maxTotalUnits(fc: BlocksCollection): number {
  let max = 0;
  for (const f of fc.features) {
    const units = Math.trunc(Number(f.properties?.total_units ?? 0)) || 0;
    if (units > max) max = units;
  }
  return max;
}

export function blockStyle(props: Partial<BlockProperties> | undefined, maxUnits: number): PathOptions {
  const buildings = Math.trunc(Number(props?.buildings ?? 0)) || 0;
  if (buildings <= 0) {
    // Empty blocks carry no data: transparent rather than painted into the scale.
    return { fillColor: 'transparent', color: '#b8b8b8', weight: 1, fillOpacity: 0 };
  }
  const units = Number(props?.total_units ?? 0) || 0;
  const scaled = maxUnits > 0 ? Math.min(Math.max(units / maxUnits, 0), 1) : 0;
  return { fillColor: greensColor(scaled), color: '#b8b8b8', weight: 1, fillOpacity: 0.7 };
}

const POPUP_FIELDS: [keyof BlockProperties, string][] = [
  ['block_label', 'Block'],
  ['buildings', 'Buildings'],
  ['total_units', '# Units'],
  ['median_year_built', 'Median year'],
  ['member_buildings', 'Buildings w/ VTU'],
  ['total_members', 'Total VTU members'],
];

function formatValue(field: keyof BlockProperties, value: unknown): string {
  if (isMissing(value)) return '';
  if (typeof value !== 'number') return String(value);
  // Folium's localize=True grouped years too ("1,965"); a year is not a quantity.
  if (field === 'median_year_built') return String(Math.round(value));
  // en-US like the rest of the ported markup, not the browser's locale (a
  // German browser would render 1.234). Non-integers keep their decimals.
  return Number.isInteger(value) ? groupThousands(value) : value.toLocaleString('en-US');
}

/** The Folium GeoJsonPopup's content: one row per field, in the same order. */
export function blockPopupHtml(props: Partial<BlockProperties>): string {
  const rows = POPUP_FIELDS.map(
    ([field, alias]) => `<tr><th>${escapeHtml(alias)}</th><td>${escapeHtml(formatValue(field, props[field]))}</td></tr>`,
  ).join('');
  return `<table class="block-popup">${rows}</table>`;
}
```

- [ ] **Step 5: Write `neighbourhoods.ts`**

```ts
/**
 * Neighbourhood outlines and name labels, ported from layout.py
 * (add_neighbourhoods_layer). Folium placed labels at a shapely centroid;
 * this uses the City's own geo_point_2d when present, so positions can
 * differ slightly.
 */
import type { PathOptions } from 'leaflet';
import { escapeHtml } from './html';
import type { BoundaryProperties } from './types';

export const NEIGHBOURHOOD_STYLE: PathOptions = { color: '#ff8c00', weight: 2, opacity: 0.9, fill: false };

export function neighbourhoodLabelHtml(name: string): string {
  return (
    '<div style="color:#ff8c00;font-weight:700;font-size:12px;' +
    'text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff;' +
    'white-space:nowrap;pointer-events:none;">' +
    escapeHtml(name) +
    '</div>'
  );
}

export function labelPosition(
  props: BoundaryProperties | null | undefined,
  fallback: [number, number],
): [number, number] {
  const p = props?.geo_point_2d;
  return p && Number.isFinite(p.lat) && Number.isFinite(p.lon) ? [p.lat, p.lon] : fallback;
}
```

- [ ] **Step 6: Write `legend.ts`**

```ts
/**
 * Neighbourhood filter tags and the block legend, ported from layout.py
 * (legends_html). Fills the containers index.html left empty. Must run
 * before wiring.js starts: it queries .filter-neighbourhood-option once.
 */
import { LEGEND_LEFT_OFFSET } from './config';
import { escapeHtml, groupThousands } from './html';
import type { FilterConfig, NeighbourhoodSummary } from './types';

export function hoodTagsHtml(hoods: NeighbourhoodSummary[] | undefined): string {
  if (!hoods || hoods.length === 0) return '<em class="filter-none">No neighbourhood data</em>';
  return hoods
    .map((n) => {
      const name = String(n.name ?? '');
      const count = groupThousands(Math.trunc(Number(n.count) || 0));
      const units = groupThousands(Math.trunc(Number(n.units) || 0));
      return (
        `<label class="filter-tag"><input type="checkbox" class="filter-neighbourhood-option" ` +
        `value="${escapeHtml(name.toLowerCase())}" checked> ${escapeHtml(name)} ` +
        `<span class="filter-tag-count">(${count} bldgs · ${units} units)</span></label>`
      );
    })
    .join('');
}

export function blockLegendMax(fc: FilterConfig): number {
  const raw = fc.blocks_total_units_max ?? fc.blocks_member_building_max;
  const n = Math.trunc(Number(raw));
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** Six ticks, 0 to max. (Python used banker's rounding; wiring.js repaints these with Math.round at start-up anyway.) */
export function blockTicks(max: number): string[] {
  if (max === 0) return Array(6).fill('0');
  return [0, 0.2, 0.4, 0.6, 0.8, 1].map((f) => groupThousands(f === 1 ? max : Math.round(max * f)));
}

export function renderLegend(fc: FilterConfig, doc: Document = document): void {
  const hoods = doc.getElementById('filter-neighbourhoods');
  if (hoods) hoods.innerHTML = hoodTagsHtml(fc.neighbourhoods);
  const max = blockLegendMax(fc);
  const scale = doc.getElementById('block-legend-scale');
  if (scale) scale.innerHTML = blockTicks(max).map((t) => `<span>${escapeHtml(t)}</span>`).join('');
  const note = doc.getElementById('block-legend-note');
  if (note) note.textContent = `Color scaled to 0–${groupThousands(max)} units (visible blocks).`;
  const legend = doc.getElementById('legend-map');
  if (legend) legend.style.left = `${LEGEND_LEFT_OFFSET}px`;
}
```

- [ ] **Step 7: Run tests and the type check**

Run: `npm test && npm run typecheck`
Expected: 30 passed (15 + 15); `tsc` reports nothing.

- [ ] **Step 8: Commit** *(ask first)*

```bash
git add frontend/src/html.ts frontend/src/html.test.ts frontend/src/blocks.ts \
        frontend/src/blocks.test.ts frontend/src/neighbourhoods.ts \
        frontend/src/neighbourhoods.test.ts frontend/src/legend.ts frontend/src/legend.test.ts
git commit -m "Port the block choropleth, block popup, neighbourhood labels and legend to TS"
```

---

### Task 7: Sidebar table rows (`tables.ts`)

Per D4, the rows are needed in step 4 because they are `wiring.js`'s filter model (Finding 8). This ports `tables.py`'s `buildings_table`/`rows_buildings`, `blocks_table`/`rows_blocks`, `landlords_table`/`rows_landlords` and `neighbourhoods_table`/`rows_neighbourhoods` (`tables.py:10-239`). Attributes and their order, columns, sort keys and rounding follow the Python. There are two known cosmetic differences, and neither changes sorting or filtering. Numeric sort values are written as JavaScript numbers (`15` where Python wrote `15.0`). Rows with tied sort keys may come out in a different order.

**Files:**
- Create: `frontend/src/tables.ts`
- Test: `frontend/src/tables.test.ts`

**Interfaces:**
- Consumes: `escapeHtml`, `isMissing`, `roundHalfEven` (Task 6); `BuildingRecord`, `BuildingData`, `BlocksCollection` (Task 4).
- Produces: `buildingRow(r: BuildingRecord): string`, `buildingRowsHtml(records: BuildingRecord[]): string`, `blockRowsHtml(fc: BlocksCollection): string`, `landlordRowsHtml(records: BuildingRecord[]): string`, `neighbourhoodRowsHtml(records: BuildingRecord[]): string`, `renderTables(data: BuildingData, blocks: BlocksCollection, doc?: Document): void`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/tables.test.ts
import { describe, expect, it } from 'vitest';
import { blockRowsHtml, buildingRow, buildingRowsHtml, landlordRowsHtml, neighbourhoodRowsHtml } from './tables';
import type { BlocksCollection, BuildingRecord } from './types';

const rec = (over: Partial<BuildingRecord>): BuildingRecord => ({
  b_id: 1, address: 'A', local_area: 'West End', block_id: 1, units: 10, member_count: 0,
  member_share_pct: 0, year_built: 1970, owner_group: 'O', owner_key: 'o', member_count_all: 0,
  value_land: 1, value_bldg: 1, bldg_land_ratio: 1, has_vtu_member: false, latest_membership_year: null,
  housing_type: '', ...over,
});

describe('buildingRow', () => {
  it("reproduces rows_buildings' markup exactly", () => {
    const row = buildingRow(rec({
      b_id: 7, address: '12 Oak & Elm St', block_id: 3.0, units: 40.0, member_count: 1,
      member_share_pct: 6, year_built: 1965.0, owner_group: 'Example "Holdings"',
      owner_key: 'example-holdings', member_count_all: 2, value_land: 5000000.4, value_bldg: 800000.0,
      bldg_land_ratio: 0.16, has_vtu_member: true, latest_membership_year: 2025.0, housing_type: 'sro',
    }));
    expect(row).toBe(
      '<tr data-bid="7" data-owner="example-holdings" data-block="3" data-area="West End" ' +
        'data-value-land="5000000" data-value-bldg="800000" data-value-ratio="0.16" data-units="40" ' +
        'data-year-built="1965" data-has-vtu-member="1" data-latest-membership-year="2025" ' +
        'data-member-total="2" data-search="12 oak &amp; elm st west end 3 40 1 example &quot;holdings&quot; sro" ' +
        'data-housing-type="sro">' +
        '<td class="select-cell"><input type="checkbox" class="row-select" data-type="building" data-target="7"></td>' +
        '<td>12 Oak &amp; Elm St</td><td data-sort-value="West End">West End</td>' +
        '<td data-sort-value="3">3</td><td data-sort-value="40">40</td><td data-sort-value="1">1</td>' +
        '<td data-sort-value="6">6%</td><td>Example &quot;Holdings&quot;</td>' +
        '<td data-sort-value="1965">1965</td><td data-sort-value="sro">sro</td></tr>',
    );
  });

  it('leaves missing values empty and keeps them out of the search text', () => {
    const row = buildingRow(rec({ b_id: 9, address: 'X', local_area: null, block_id: null, units: null, year_built: null }));
    expect(row).toContain('data-block="" data-area=""');
    expect(row).toContain('data-units="" data-year-built=""');
    expect(row).toContain('data-search="x 0 o"');
  });
});

describe('buildingRowsHtml', () => {
  it('sorts by members then units, descending, with missing units last', () => {
    const html = buildingRowsHtml([
      rec({ b_id: 1, member_count: 0, units: 5 }),
      rec({ b_id: 2, member_count: 1, units: null }),
      rec({ b_id: 3, member_count: 1, units: 50 }),
      rec({ b_id: 4, member_count: 0, units: 90 }),
    ]);
    expect([...html.matchAll(/data-bid="(\d+)"/g)].map((m) => m[1])).toEqual(['3', '2', '4', '1']);
  });
});

describe('blockRowsHtml', () => {
  it('sorts labelled blocks before (Unknown) ones and rounds like pandas', () => {
    const fc = { type: 'FeatureCollection', schema_version: 1, features: [
      { type: 'Feature', geometry: null, properties: { block_id: 5, block_label: '(Unknown)-01', local_area: null, buildings: 0, total_units: 0, median_year_built: null, member_buildings: 0 } },
      { type: 'Feature', geometry: null, properties: { block_id: 6, block_label: 'West End-02', local_area: 'West End', buildings: 2, total_units: 25, median_year_built: 1966.5, member_buildings: 1 } },
    ] } as unknown as BlocksCollection;
    const html = blockRowsHtml(fc);
    expect([...html.matchAll(/data-block="(\d+)"/g)].map((m) => m[1])).toEqual(['6', '5']);
    expect(html).toContain('<td data-sort-value="12.5">12.5</td>'); // avg units
    expect(html).toContain('<td data-sort-value="1966">1966</td>'); // 1966.5 -> 1966 (half to even)
  });
});

describe('group tables', () => {
  const records = [
    rec({ b_id: 1, owner_group: 'B Co', owner_key: 'b', units: 10, has_vtu_member: true, local_area: 'West End' }),
    rec({ b_id: 2, owner_group: 'A Co', owner_key: 'a', units: 30, local_area: null }),
    rec({ b_id: 3, owner_group: 'B Co', owner_key: 'b', units: 5, local_area: 'West End' }),
  ];

  it('groups landlords by owner, sorted by total units', () => {
    const html = landlordRowsHtml(records);
    expect([...html.matchAll(/data-owner="([^"]+)"/g)].map((m) => m[1])).toEqual(['a', 'b']);
    expect(html).toContain('data-owner="b" data-bldgs="2" data-units="15" data-vtu-bldgs="1"');
  });

  it('groups neighbourhoods, putting missing areas under (Unknown)', () => {
    const html = neighbourhoodRowsHtml(records);
    expect([...html.matchAll(/<tr data-area="([^"]+)"/g)].map((m) => m[1])).toEqual(['(Unknown)', 'West End']);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm test`
Expected: FAIL, `Failed to resolve import "./tables"`.

- [ ] **Step 3: Write `tables.ts`**

```ts
/**
 * Sidebar table rows, ported from sica_mapping/data/tables.py. Attributes,
 * columns, sort keys and rounding follow the Python, because wiring.js reads
 * these rows as its filter model: data-* attributes, fixed column indices
 * (wiring.js cacheRowCells) and .row-select checkboxes. Known cosmetic
 * differences, neither affecting sorting or filtering: numeric sort values
 * render as JS numbers (15, not Python's 15.0), and tied rows may order
 * differently. Must render before wiring.js starts; it queries the rows once.
 */
import { escapeHtml, isMissing, roundHalfEven } from './html';
import type { BlocksCollection, BuildingData, BuildingRecord } from './types';

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
/** Python int() of a present number, else "". */
const intStr = (v: unknown): string => {
  const n = num(v);
  return n === null ? '' : String(Math.trunc(n));
};
const text = (v: unknown): string => (isMissing(v) ? '' : String(v));

/** pandas sort_values(ascending=False): larger first, missing last. Stable. */
function descMissingLast(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return b - a;
}

/** Python's str ordering (code points), not localeCompare. */
function byCodePoint(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

export function buildingRow(r: BuildingRecord): string {
  const bid = Math.trunc(Number(r.b_id));
  const block = intStr(r.block_id);
  const units = intStr(r.units);
  const year = intStr(r.year_built);
  const membershipYear = intStr(r.latest_membership_year);
  const land = num(r.value_land);
  const bldg = num(r.value_bldg);
  const ratio = num(r.bldg_land_ratio);
  const valLand = land === null ? '' : String(roundHalfEven(land));
  const valBldg = bldg === null ? '' : String(roundHalfEven(bldg));
  const ratioVal = ratio === null ? '' : String(roundHalfEven(ratio, 3));
  const memberCount = Math.trunc(num(r.member_count) ?? 0);
  const memberTotal = Math.trunc(num(r.member_count_all) ?? memberCount);
  const sharePct = Math.trunc(num(r.member_share_pct) ?? 0); // already rounded half-even by the export
  const area = text(r.local_area);
  const housing = text(r.housing_type);
  const owner = text(r.owner_group);
  const search = [text(r.address), area, block, units, String(memberCount), owner, housing]
    .filter((v) => v !== '')
    .map((v) => v.toLowerCase())
    .join(' ');
  const a = escapeHtml(area);
  const h = escapeHtml(housing);
  return (
    `<tr data-bid="${bid}" data-owner="${escapeHtml(text(r.owner_key))}" data-block="${block}" ` +
    `data-area="${a}" ` +
    `data-value-land="${valLand}" data-value-bldg="${valBldg}" ` +
    `data-value-ratio="${ratioVal}" data-units="${units}" ` +
    `data-year-built="${year}" ` +
    `data-has-vtu-member="${r.has_vtu_member ? 1 : 0}" ` +
    `data-latest-membership-year="${membershipYear}" ` +
    `data-member-total="${memberTotal}" data-search="${escapeHtml(search)}" ` +
    `data-housing-type="${h}">` +
    `<td class="select-cell"><input type="checkbox" class="row-select" ` +
    `data-type="building" data-target="${bid}"></td>` +
    `<td>${escapeHtml(text(r.address))}</td>` +
    `<td data-sort-value="${a}">${a}</td>` +
    `<td data-sort-value="${block}">${block}</td>` +
    `<td data-sort-value="${units}">${units}</td>` +
    `<td data-sort-value="${memberCount}">${memberCount}</td>` +
    `<td data-sort-value="${sharePct}">${sharePct}%</td>` +
    `<td>${escapeHtml(owner)}</td>` +
    `<td data-sort-value="${year}">${year}</td>` +
    `<td data-sort-value="${h}">${h}</td>` +
    `</tr>`
  );
}

export function buildingRowsHtml(records: BuildingRecord[]): string {
  return [...records]
    .sort(
      (x, y) =>
        descMissingLast(num(x.member_count), num(y.member_count)) || descMissingLast(num(x.units), num(y.units)),
    )
    .map(buildingRow)
    .join('\n');
}

const avgUnits = (total: number, bldgs: number): number => (bldgs > 0 ? roundHalfEven(total / bldgs, 1) : 0);

export function blockRowsHtml(fc: BlocksCollection): string {
  const rows = fc.features.map((f) => f.properties ?? ({} as BlocksCollection['features'][number]['properties']));
  return rows
    .map((p) => ({ p, label: text(p.block_label) }))
    .sort((x, y) => {
      const ux = x.label.startsWith('(Unknown)') ? 1 : 0;
      const uy = y.label.startsWith('(Unknown)') ? 1 : 0;
      return ux - uy || byCodePoint(x.label, y.label);
    })
    .map(({ p, label }) => {
      const id = Math.trunc(Number(p.block_id));
      const bldgs = Math.trunc(num(p.buildings) ?? 0);
      const totalRaw = num(p.total_units) ?? 0;
      const total = Math.trunc(totalRaw);
      const avg = avgUnits(totalRaw, bldgs);
      const median = num(p.median_year_built);
      const year = median === null ? '' : String(roundHalfEven(median));
      const vtu = Math.trunc(num(p.member_buildings) ?? 0);
      const l = escapeHtml(label);
      return (
        `<tr data-block="${id}" data-area="${escapeHtml(text(p.local_area))}" ` +
        `data-bldgs="${bldgs}" data-units="${total}" ` +
        `data-vtu-bldgs="${vtu}">` +
        `<td class="select-cell"><input type="checkbox" class="row-select" ` +
        `data-type="block" data-target="${id}"></td>` +
        `<td data-sort-value="${l}">${l}</td>` +
        `<td data-sort-value="${bldgs}">${bldgs}</td>` +
        `<td data-sort-value="${total}">${total}</td>` +
        `<td data-sort-value="${avg}">${avg.toFixed(1)}</td>` +
        `<td data-sort-value="${year}">${year}</td>` +
        `<td data-sort-value="${vtu}">${vtu}</td>` +
        `</tr>`
      );
    })
    .join('\n');
}

interface Group {
  label: string;
  key: string;
  buildings: number;
  totalUnits: number;
  memberBuildings: number;
}

/** pandas groupby(...).agg(count address, sum units, sum has_vtu_member), then sort by units, buildings desc. */
function aggregate(records: BuildingRecord[], labelOf: (r: BuildingRecord) => string, keyOf: (r: BuildingRecord) => string): Group[] {
  const groups = new Map<string, Group>();
  for (const r of records) {
    const label = labelOf(r);
    const key = keyOf(r);
    const id = `${label}\u0000${key}`;
    let g = groups.get(id);
    if (!g) {
      g = { label, key, buildings: 0, totalUnits: 0, memberBuildings: 0 };
      groups.set(id, g);
    }
    if (!isMissing(r.address)) g.buildings += 1;
    g.totalUnits += num(r.units) ?? 0;
    if (r.has_vtu_member === true) g.memberBuildings += 1;
  }
  return [...groups.values()]
    .sort((a, b) => byCodePoint(a.label, b.label) || byCodePoint(a.key, b.key)) // groupby's key order
    .sort((a, b) => b.totalUnits - a.totalUnits || b.buildings - a.buildings);
}

function groupRow(g: Group, type: 'owner' | 'neighbourhood', target: string, first: string, dataKey: string): string {
  const units = Math.trunc(g.totalUnits);
  const avg = avgUnits(g.totalUnits, g.buildings);
  return (
    `<tr ${dataKey}="${target}" ` +
    `data-bldgs="${g.buildings}" data-units="${units}" ` +
    `data-vtu-bldgs="${g.memberBuildings}">` +
    `<td class="select-cell"><input type="checkbox" class="row-select" ` +
    `data-type="${type}" data-target="${target}"></td>` +
    `<td>${first}</td>` +
    `<td data-sort-value="${g.buildings}">${g.buildings}</td>` +
    `<td data-sort-value="${units}">${units}</td>` +
    `<td data-sort-value="${avg}">${avg.toFixed(1)}</td>` +
    `<td data-sort-value="${g.memberBuildings}">${g.memberBuildings}</td>` +
    `</tr>`
  );
}

export function landlordRowsHtml(records: BuildingRecord[]): string {
  return aggregate(
    records,
    (r) => (isMissing(r.owner_group) ? '(Unknown)' : String(r.owner_group)),
    (r) => (isMissing(r.owner_key) ? 'unknown' : String(r.owner_key)),
  )
    .map((g) => groupRow(g, 'owner', escapeHtml(g.key), escapeHtml(g.label), 'data-owner'))
    .join('\n');
}

export function neighbourhoodRowsHtml(records: BuildingRecord[]): string {
  return aggregate(
    records,
    (r) => (isMissing(r.local_area) ? '(Unknown)' : String(r.local_area)),
    () => '',
  )
    .map((g) => {
      const area = escapeHtml(g.label);
      return groupRow(g, 'neighbourhood', area, area, 'data-area');
    })
    .join('\n');
}

export function renderTables(data: BuildingData, blocks: BlocksCollection, doc: Document = document): void {
  const records = Object.values(data.records);
  const fill = (tableId: string, html: string) => {
    const tbody = doc.querySelector(`#${tableId} tbody`);
    if (tbody) tbody.innerHTML = html;
  };
  fill('buildings-table', buildingRowsHtml(records));
  fill('blocks-table', blockRowsHtml(blocks));
  fill('landlords-table', landlordRowsHtml(records));
  fill('neighbourhoods-table', neighbourhoodRowsHtml(records));
}
```

- [ ] **Step 4: Run tests and the type check**

Run: `npm test && npm run typecheck`
Expected: 36 passed (30 + 6); `tsc` reports nothing.

- [ ] **Step 5: Commit** *(ask first)*

```bash
git add frontend/src/tables.ts frontend/src/tables.test.ts
git commit -m "Port the sidebar table rows from tables.py to tables.ts"
```

---

### Task 8: Move `wiring.js` in and write `bootstrap.ts` — the full map renders

Spec §9 step 4's end state: `npm run dev` renders the full map. Per D1, `wiring.js` gets an exported entry point. The patch below is the one prototyped during planning: every replacement matches exactly once, and the result parses as an ES module.

**Files:**
- Create: `frontend/src/wiring.js` (patched copy of `src/sica_mapping/frontend/templates/wiring.js`, which stays in place for the Folium build)
- Create: `frontend/src/wiring.d.ts`, `frontend/src/layers.ts`, `frontend/src/bootstrap.ts`

**Interfaces:**
- Consumes: everything from Tasks 4–7.
- Produces: `startWiring(ctx: WiringContext): void` from `wiring.js`, where `WiringContext = { map; layers: { blocks; vtu; non; neighbourhoods }; markersById; ringsById; filterConfig; markers: StyledMarker[]; buildingData }`. `layers.ts`: `createBlocksLayer(fc)`, `createNeighbourhoodsLayer(fc)`, `createBuildingLayers(markers, bindPopup?)`.

- [ ] **Step 1: Copy and patch `wiring.js`**

Run from the repo root. Each replacement asserts it matched exactly once:

```bash
uv run python - <<'EOF'
from pathlib import Path

src = Path("src/sica_mapping/frontend/templates/wiring.js")
dst = Path("frontend/src/wiring.js")
s = src.read_text()


def rep(old, new):
    global s
    n = s.count(old)
    assert n == 1, f"expected 1 occurrence, found {n}: {old[:70]!r}"
    s = s.replace(old, new)


# 1. <script> wrapper + self-invoking function -> exported entry point.
rep("\n<script>\n(function() {\n", "export function startWiring(ctx) {\n")
rep("\n})();\n</script>\n", "\n}\n")

# 2. bootstrap.ts fetches the artifacts once, schema-checked; no URLs here.
rep("""  const DATA_URLS = {
    filterConfig: '$filter_config_url',
    markerMetadata: '$marker_metadata_url',
    buildingData: '$building_records_url',
  };

  function fetchJson(url) {
    return fetch(url, { cache: 'no-cache' }).then(function(resp) {
      if (!resp.ok) {
        throw new Error('Failed to load ' + url + ': ' + resp.status);
      }
      return resp.json();
    });
  }

""", "")

# 3. Layers and map from the context — not Folium's window globals, not Leaflet's private _map.
rep("""      const layerBlocks = window["$blocks_layer_var"] || null;
      const layerVTU = window["$layer_vtu_var"] || null;
      const layerNon = window["$layer_non_var"] || null;
      const layerNeighbourhoods = window["$layer_neighbourhoods_var"] || null;
      const mapInstance = (layerBlocks && layerBlocks._map) || (layerVTU && layerVTU._map) || (layerNon && layerNon._map) || null;
""", """      const layerBlocks = ctx.layers.blocks;
      const layerVTU = ctx.layers.vtu;
      const layerNon = ctx.layers.non;
      const layerNeighbourhoods = ctx.layers.neighbourhoods;
      const mapInstance = ctx.map;
""")

# 4. Markers by b_id, not by Folium variable name.
rep("""          var markerVar = meta.marker_var;
          if (!markerVar) return;
          var marker = window[String(markerVar)];
          if (!marker) return;
""", """          var marker = ctx.markersById[String(meta.b_id)];
          if (!marker) return;
""")

# 5. Extra housing-type rings likewise.
rep("""          if (Array.isArray(meta.extra_rings) && meta.extra_rings.length) {
            marker._extraRings = meta.extra_rings
              .map(function(er) {
                return { housingType: er.housing_type, marker: window[String(er.marker_var)] };
              })
              .filter(function(r) { return !!r.marker; });
          }
""", """          var rings = ctx.ringsById[String(meta.b_id)];
          if (rings && rings.length) {
            marker._extraRings = rings.map(function(r) {
              return { housingType: r.housing_type, marker: r.marker };
            });
          }
""")

# 6. '$$' was string.Template's escape for '$'; nothing substitutes this file now.
rep("return '$$' + Math.round(value).toLocaleString();", "return '$' + Math.round(value).toLocaleString();")

# 7. Start-up from the context instead of fetching.
rep("""  function loadInitialData() {
    return Promise.all([
      fetchJson(DATA_URLS.filterConfig),
      fetchJson(DATA_URLS.markerMetadata),
      fetchJson(DATA_URLS.buildingData),
    ]).then(function(results) {
      assignLoadedData(results[0], results[1], results[2]);
    });
  }

  loadInitialData()
    .then(function() {
      if (document.readyState === 'complete') {
        wireUp();
      } else {
        window.addEventListener('load', wireUp);
      }
    })
    .catch(function(err) {
      console.error('Failed to initialise map data', err);
    });
""", """  assignLoadedData(ctx.filterConfig, ctx.markers, ctx.buildingData);
  if (document.readyState === 'complete') {
    wireUp();
  } else {
    window.addEventListener('load', wireUp);
  }
""")

leftover = [t for t in ("$filter_config_url", "$marker_metadata_url", "$building_records_url",
                        "$blocks_layer_var", "$layer_vtu_var", "$layer_non_var",
                        "$layer_neighbourhoods_var", "marker_var", "<script", "</script", "'$$'")
            if t in s]
assert not leftover, leftover
dst.write_text(s)
print(f"wrote {dst} ({len(s.splitlines())} lines)")
EOF
node --check frontend/src/wiring.js   # ESM: frontend/package.json has "type": "module"
diff src/sica_mapping/frontend/templates/wiring.js frontend/src/wiring.js | grep -c '^[<>]'
```

Expected: `wrote frontend/src/wiring.js (1891 lines)`, the check passes, and 74 changed lines. Nothing else in the file changes. Its comments still mention Folium in places; leave them.

- [ ] **Step 2: Write `wiring.d.ts`**

```ts
// frontend/src/wiring.d.ts — types for wiring.js, which stays JavaScript (spec §2).
import type { CircleMarker, FeatureGroup, GeoJSON, Map } from 'leaflet';
import type { StyledMarker } from './markers';
import type { BuildingData, FilterConfig } from './types';

export interface WiringContext {
  map: Map;
  layers: { blocks: GeoJSON; vtu: FeatureGroup; non: FeatureGroup; neighbourhoods: FeatureGroup };
  markersById: Record<string, CircleMarker>;
  ringsById: Record<string, { housing_type: string; marker: CircleMarker }[]>;
  filterConfig: FilterConfig;
  markers: StyledMarker[];
  buildingData: BuildingData;
}

export function startWiring(ctx: WiringContext): void;
```

- [ ] **Step 3: Write `layers.ts`**

```ts
/** Every Leaflet constructor lives here (and in bootstrap.ts); the modules it uses are pure and unit-tested. */
import * as L from 'leaflet';
import { blockPopupHtml, blockStyle, maxTotalUnits } from './blocks';
import { RING_OPACITY, RING_SPACING, RING_WEIGHT, ringColor, type StyledMarker } from './markers';
import { NEIGHBOURHOOD_STYLE, labelPosition, neighbourhoodLabelHtml } from './neighbourhoods';
import type { BlocksCollection, BoundaryCollection } from './types';

export function createBlocksLayer(fc: BlocksCollection): L.GeoJSON {
  const maxUnits = maxTotalUnits(fc);
  return L.geoJSON(fc, {
    style: (feature) => blockStyle(feature?.properties, maxUnits),
    onEachFeature: (feature, layer) => {
      layer.bindPopup(() => blockPopupHtml(feature.properties ?? {}));
    },
  });
}

export function createNeighbourhoodsLayer(fc: BoundaryCollection): L.FeatureGroup {
  const group = L.featureGroup();
  for (const feature of fc.features) {
    const outline = L.geoJSON(feature, { style: () => NEIGHBOURHOOD_STYLE }).addTo(group);
    const centre = outline.getBounds().getCenter();
    L.marker(labelPosition(feature.properties, [centre.lat, centre.lng]), {
      // className 'empty', as Folium's DivIcon: no default white box.
      icon: L.divIcon({ html: neighbourhoodLabelHtml(String(feature.properties?.name ?? '')), iconSize: [0, 0], className: 'empty' }),
      interactive: false,
      keyboard: false,
    }).addTo(group);
  }
  return group;
}

export interface BuildingLayers {
  vtu: L.FeatureGroup;
  non: L.FeatureGroup;
  markersById: Record<string, L.CircleMarker>;
  ringsById: Record<string, { housing_type: string; marker: L.CircleMarker }[]>;
}

/**
 * Two groups (VTU / non-VTU), as add_buildings_layers built them. Markers go
 * into the groups first; the caller adds the groups to the map afterwards,
 * non-VTU then VTU, which is what sets their paint order on the shared canvas.
 */
export function createBuildingLayers(
  markers: StyledMarker[],
  bindPopup?: (marker: L.CircleMarker, m: StyledMarker) => void,
): BuildingLayers {
  const vtu = L.featureGroup();
  const non = L.featureGroup();
  const markersById: BuildingLayers['markersById'] = {};
  const ringsById: BuildingLayers['ringsById'] = {};
  for (const m of markers) {
    if (m.lat === null || m.lon === null) continue;
    const target = m.is_vtu ? vtu : non;
    const key = String(m.b_id);
    // Extra rings first, so they paint underneath the building as a halo.
    const rings = m.extra_rings.map((ring, i) => {
      const marker = L.circleMarker([m.lat as number, m.lon as number], {
        radius: m.base_radius + RING_SPACING * (i + 1),
        fill: false,
        color: ringColor(ring.housing_type),
        weight: RING_WEIGHT,
        opacity: RING_OPACITY,
      });
      target.addLayer(marker);
      return { housing_type: ring.housing_type, marker };
    });
    if (rings.length) ringsById[key] = rings;
    const marker = L.circleMarker([m.lat, m.lon], {
      radius: m.base_radius,
      fill: true,
      fillOpacity: m.base_opacity,
      color: m.stroke_color,
      weight: m.stroke_weight,
      fillColor: m.base_color,
    });
    bindPopup?.(marker, m);
    target.addLayer(marker);
    markersById[key] = marker;
  }
  return { vtu, non, markersById, ringsById };
}
```

- [ ] **Step 4: Write `bootstrap.ts`**

```ts
/**
 * Entry point: load the artifacts once, build the map, render the sidebar
 * rows and legend, then hand everything to wiring.js. Order matters —
 * wiring.js queries the table rows and neighbourhood filter inputs once, so
 * those render first.
 */
import 'leaflet/dist/leaflet.css';
// Folium's page loaded Bootstrap; the sidebar's font, box-sizing and spacing
// come from its reboot layer (no Bootstrap classes or JS are used).
import 'bootstrap/dist/css/bootstrap-reboot.min.css';
import * as L from 'leaflet';
import { BASEMAPS, DEFAULT_BASEMAP, DEFAULT_CENTER, DEFAULT_ZOOM } from './config';
import { loadArtifacts } from './data';
import { createBlocksLayer, createBuildingLayers, createNeighbourhoodsLayer } from './layers';
import { renderLegend } from './legend';
import { markerStyle } from './markers';
import { renderTables } from './tables';
import { startWiring } from './wiring.js';

function showLoadError(err: unknown): void {
  console.error('Failed to initialise the map', err);
  const el = document.createElement('div');
  el.id = 'load-error';
  el.textContent = `Map failed to load: ${err instanceof Error ? err.message : String(err)}`;
  document.body.appendChild(el);
}

async function main(): Promise<void> {
  const artifacts = await loadArtifacts();

  const map = L.map('map', { preferCanvas: true }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
  const basemap = BASEMAPS[DEFAULT_BASEMAP];
  L.tileLayer(basemap.tiles, { attribution: basemap.attribution }).addTo(map);
  if (basemap.labels) L.tileLayer(basemap.labels, { attribution: basemap.attribution }).addTo(map);

  // Same order Folium added them: blocks, neighbourhoods, then buildings.
  const blocks = createBlocksLayer(artifacts.blocks).addTo(map);
  const neighbourhoods = createNeighbourhoodsLayer(artifacts.boundaries).addTo(map);
  const styled = artifacts.markers.map((m) => ({ ...m, ...markerStyle(m) }));
  const buildings = createBuildingLayers(styled);
  buildings.non.addTo(map);
  buildings.vtu.addTo(map);

  const b = artifacts.filterConfig.bounds;
  if (b) map.fitBounds([[b.lat_min, b.lon_min], [b.lat_max, b.lon_max]]);

  renderLegend(artifacts.filterConfig);
  renderTables(artifacts.buildingData, artifacts.blocks);

  startWiring({
    map,
    layers: { blocks, vtu: buildings.vtu, non: buildings.non, neighbourhoods },
    markersById: buildings.markersById,
    ringsById: buildings.ringsById,
    filterConfig: artifacts.filterConfig,
    markers: styled,
    buildingData: artifacts.buildingData,
  });
}

main().catch(showLoadError);
```

- [ ] **Step 5: Type check and unit tests**

Run: `npm run typecheck && npm test`
Expected: `tsc` reports nothing; 36 passed.

- [ ] **Step 6: Run it against the real artifacts**

```bash
cd .. && uv run python scripts/rebuild_map.py --skip-ingest && cd frontend
npm run dev
```

Open the printed URL. This is a quick smoke test; the full comparison is Task 10. Confirm:
- The map fits Vancouver, with greens on blocks, pink/grey markers, blue/orange rings and orange neighbourhood outlines with labels.
- All four sidebar tabs have rows. Filters, sliders (currency labels show a single `$`), search and the layer toggles all work.
- Clicking a block opens its popup. (Building popups arrive in Task 9.)
- The browser console shows no errors, and no `wireUp() failed after … attempts`.

If the page shows the red `#load-error` banner, its message names the failing artifact.

- [ ] **Step 7: Build and check the output size**

```bash
npm run build
ls -la dist dist/data
python3 - <<'EOF'
import gzip
from pathlib import Path
gz = lambda f: len(gzip.compress(f.read_bytes(), 6))
data = sum(gz(f) for f in Path("dist/data").iterdir())
page = sum(gz(f) for f in Path("dist").rglob("*") if f.is_file() and "data" not in f.relative_to("dist").parts)
print(f"dist/data  {data / 1e6:5.2f} MB gz")
print(f"page+code  {page / 1e6:5.2f} MB gz")
print(f"total      {(data + page) / 1e6:5.2f} MB gz   (Folium page: ~4.2 MB gz)")
assert data < 2.5e6, "artifact transfer above 2.5 MB gzipped: are coordinates rounded (Task 2)?"
EOF
```

Expected: `dist/index.html` is tens of KB, not 22 MB. `dist/data/` holds the five artifacts, about 2.05 MB gzipped (measured during planning) and under the 2.5 MB assertion. Record the three printed totals in the task report.

- [ ] **Step 8: Commit** *(ask first)*

```bash
cd ..
git add frontend/src/wiring.js frontend/src/wiring.d.ts frontend/src/layers.ts frontend/src/bootstrap.ts
git commit -m "Move wiring.js into the frontend and render the full map from the artifacts"
```

---

### Task 9: The redesigned building popup (`popup.ts`)

Spec §7 and §9 step 5. Per D6, the 11 fields are already in `building_records.json`. This task adds a regression test for that, then builds the popup: it leads with ownership, has conditional sections, uses one escape helper and binds lazily. **Membership is not in the popup**, as an editorial choice. That is not a privacy control (spec §7 and §12), and must not be described as one.

**Files:**
- Create: `frontend/src/popup.ts`, `frontend/src/popup.css`
- Modify: `frontend/src/bootstrap.ts` (bind popups, import the CSS)
- Test: `frontend/src/popup.test.ts`, `tests/test_export_artifacts.py` (one test added)

**Interfaces:**
- Consumes: `escapeHtml`, `isMissing` (Task 6); `BuildingRecord` (Task 4); `createBuildingLayers(markers, bindPopup)` (Task 8).
- Produces: `formatCurrencyCompact(v: number): string`, `safeUrl(v: unknown): string | null`, `renderPopup(r: BuildingRecord): string`.

- [ ] **Step 1: Add the contract regression test (Python)**

Append to `tests/test_export_artifacts.py`:

```python
POPUP_FIELDS = [
    "housing_name", "portfolio_name", "portfolio_building_count", "portfolio_entities",
    "coop_status", "coop_ownership_model", "coop_url",
    "sro_owner", "sro_operator", "sro_occupancy_status", "sro_registered_rooms",
]


def test_building_records_carry_the_popup_fields(tmp_path):
    """Spec §7: the redesigned popup reads these 11 fields from building_records.json."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)

    export_artifacts(conn, tmp_path)

    columns = json.loads((tmp_path / "building_records.json").read_text())["columns"]
    missing = [f for f in POPUP_FIELDS if f not in columns]
    assert missing == []
```

Run: `uv run pytest tests/test_export_artifacts.py -v`
Expected: PASS immediately. This is a guard on an existing contract (D6), not a red-green cycle.

- [ ] **Step 2: Write the failing frontend test**

```ts
// frontend/src/popup.test.ts
import { describe, expect, it } from 'vitest';
import { formatCurrencyCompact, renderPopup, safeUrl } from './popup';
import type { BuildingRecord } from './types';

const building: BuildingRecord = {
  b_id: 1, address: '1234 Davie St', housing_name: null, owner_group: 'Hollyburn Properties',
  portfolio_name: 'Hollyburn Properties', portfolio_building_count: 23, portfolio_entities: ['a', 'b', 'c', 'd', 'e', 'f'],
  units: 87.0, year_built: 1974.0, local_area: 'West End', value_land: 20100000, value_bldg: 950000,
  is_coop: false, is_sro: false, member_count: 2, member_count_all: 3, has_vtu_member: true,
};

describe('renderPopup', () => {
  it('leads with the ownership story', () => {
    const html = renderPopup(building);
    expect(html.indexOf('Hollyburn Properties')).toBeLessThan(html.indexOf('87 units'));
    expect(html).toContain('Portfolio: 23 buildings, 6 linked entities');
    expect(html).toContain('87 units · built 1974');
    expect(html).toContain('Assessed $20.1M land · $950K building');
  });

  it('carries no membership data (editorial choice, spec §7)', () => {
    expect(renderPopup(building)).not.toMatch(/member|VTU/i);
  });

  it('shows co-op and SRO sections only when they apply', () => {
    expect(renderPopup(building)).not.toMatch(/Co-op|SRO/);
    const html = renderPopup({
      ...building, is_coop: true, coop_status: 'Active', coop_ownership_model: 'Leasehold',
      coop_url: 'https://example.org/c', is_sro: true, sro_owner: 'X Ltd', sro_operator: 'Y Soc',
      sro_occupancy_status: 'Open', sro_registered_rooms: '42',
    });
    expect(html).toContain('Co-op · Active (Leasehold)');
    expect(html).toContain('<a href="https://example.org/c" target="_blank" rel="noopener">more info</a>');
    expect(html).toContain('SRO/SRA · Owner X Ltd · Operator Y Soc · Open · 42 rooms');
  });

  it('omits missing facts rather than printing blanks', () => {
    const html = renderPopup({ b_id: 9, address: '300 Invented Rd', owner_group: '(Unknown)', units: null, year_built: null });
    expect(html).not.toMatch(/units|built|Assessed|Portfolio|null|undefined/);
  });

  it('escapes every value', () => {
    const html = renderPopup({ ...building, address: '<img src=x onerror=alert(1)>', owner_group: 'A & B' });
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
    expect(html).toContain('A &amp; B');
    expect(html).not.toContain('<img');
  });
});

describe('helpers', () => {
  it('formats assessed values compactly', () => {
    expect(formatCurrencyCompact(20186619)).toBe('$20.2M');
    expect(formatCurrencyCompact(950000)).toBe('$950K');
    expect(formatCurrencyCompact(640)).toBe('$640');
  });

  it('only links http(s) URLs', () => {
    expect(safeUrl('https://example.org/x')).toBe('https://example.org/x');
    expect(safeUrl('javascript:alert(1)')).toBeNull();
    expect(safeUrl('not a url')).toBeNull();
    expect(safeUrl(null)).toBeNull();
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `npm test`
Expected: FAIL, `Failed to resolve import "./popup"`.

- [ ] **Step 4: Write `popup.ts` and `popup.css`**

`frontend/src/popup.ts`:

```ts
/**
 * The building popup, redesigned per spec §7: leads with ownership (the
 * project's differentiator), sections appear only when their data does,
 * every value goes through one escape helper. Membership is deliberately
 * absent — an editorial choice, NOT a privacy control: membership remains
 * in the artifacts and in marker colour (spec §12).
 */
import { escapeHtml, isMissing } from './html';
import type { BuildingRecord } from './types';

const str = (v: unknown): string => (isMissing(v) ? '' : String(v).trim());
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

export function formatCurrencyCompact(v: number): string {
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${Math.round(v / 1e3).toLocaleString('en-US')}K`;
  return `$${Math.round(v)}`;
}

/** The URL if it is http(s), else null — never link javascript: or other schemes. */
export function safeUrl(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  try {
    const u = new URL(v);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null;
  } catch {
    return null;
  }
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const div = (cls: string, html: string) => `<div${cls ? ` class="${cls}"` : ''}>${html}</div>`;

export function renderPopup(r: BuildingRecord): string {
  const head = [div('popup-address', escapeHtml(str(r.address)))];
  if (str(r.housing_name)) head.push(div('popup-name', escapeHtml(str(r.housing_name))));

  const ownership: string[] = [];
  if (str(r.owner_group)) ownership.push(div('popup-owner', escapeHtml(str(r.owner_group))));
  if (str(r.portfolio_name)) {
    const count = num(r.portfolio_building_count);
    const entities = Array.isArray(r.portfolio_entities) ? r.portfolio_entities.length : 0;
    const size = count === null ? 'Portfolio' : `Portfolio: ${plural(Math.trunc(count), 'building', 'buildings')}`;
    ownership.push(div('', escapeHtml(`${size}, ${plural(entities, 'linked entity', 'linked entities')}`)));
  }

  const facts: string[] = [];
  const units = num(r.units);
  const year = num(r.year_built);
  const sizeLine = [
    units === null ? '' : `${Math.trunc(units).toLocaleString('en-US')} units`,
    year === null ? '' : `built ${Math.trunc(year)}`,
  ].filter(Boolean).join(' · ');
  if (sizeLine) facts.push(div('', escapeHtml(sizeLine)));
  if (str(r.local_area)) facts.push(div('', escapeHtml(str(r.local_area))));
  const land = num(r.value_land);
  const bldg = num(r.value_bldg);
  const assessed = [
    land === null ? '' : `${formatCurrencyCompact(land)} land`,
    bldg === null ? '' : `${formatCurrencyCompact(bldg)} building`,
  ].filter(Boolean).join(' · ');
  if (assessed) facts.push(div('', escapeHtml(`Assessed ${assessed}`)));

  const housing: string[] = [];
  if (r.is_coop === true) {
    let line = 'Co-op';
    if (str(r.coop_status)) line += ` · ${str(r.coop_status)}`;
    if (str(r.coop_ownership_model)) line += ` (${str(r.coop_ownership_model)})`;
    let html = escapeHtml(line);
    const url = safeUrl(r.coop_url);
    if (url) html += ` · <a href="${escapeHtml(url)}" target="_blank" rel="noopener">more info</a>`;
    housing.push(div('', html));
  }
  if (r.is_sro === true) {
    const parts = ['SRO/SRA'];
    if (str(r.sro_owner)) parts.push(`Owner ${str(r.sro_owner)}`);
    if (str(r.sro_operator)) parts.push(`Operator ${str(r.sro_operator)}`);
    if (str(r.sro_occupancy_status)) parts.push(str(r.sro_occupancy_status));
    if (str(r.sro_registered_rooms)) parts.push(`${str(r.sro_registered_rooms)} rooms`);
    housing.push(div('', escapeHtml(parts.join(' · '))));
  }

  const sections = [head, ownership, facts, housing]
    .filter((s) => s.length)
    .map((s) => div('popup-section', s.join('')));
  return div('sica-popup', sections.join(''));
}
```

`frontend/src/popup.css`:

```css
.sica-popup { font-size: 13px; line-height: 1.4; min-width: 200px; }
.sica-popup .popup-section + .popup-section { border-top: 1px solid #ddd; margin-top: 6px; padding-top: 6px; }
.sica-popup .popup-address { font-weight: 700; }
.sica-popup .popup-name { color: #555; }
.sica-popup .popup-owner { font-weight: 600; }
```

- [ ] **Step 5: Bind popups lazily in `bootstrap.ts`**

Add the imports:

```ts
import './popup.css';
import { renderPopup } from './popup';
```

Replace `const buildings = createBuildingLayers(styled);` with:

```ts
  const records = artifacts.buildingData.records;
  // Lazy: the markup is built on first open, from the one record the table and filters also read.
  const buildings = createBuildingLayers(styled, (marker, m) => {
    marker.bindPopup(() => renderPopup(records[String(m.b_id)] ?? { b_id: m.b_id }), { maxWidth: 320 });
  });
```

- [ ] **Step 6: Run the tests and the type check**

Run: `npm test && npm run typecheck`, then `cd .. && uv run pytest -q`
Expected: 43 frontend tests passed (36 + 7); `tsc` reports nothing; Python suite 64 passed (63 + 1).

- [ ] **Step 7: Check popups in the browser**

Run `npm run dev` and open popups for: a co-op, an SRO, a building whose owner has a portfolio, and one of the 153 overlay-only records (grey markers with rings and no units). Confirm the sections match spec §7's sketch.

- [ ] **Step 8: Commit** *(ask first)*

```bash
git add frontend/src/popup.ts frontend/src/popup.css frontend/src/popup.test.ts \
        frontend/src/bootstrap.ts tests/test_export_artifacts.py
git commit -m "Add the redesigned, lazily bound building popup"
```

---

### Task 10: Parity check — then STOP

Spec §9 step 6 and §11. Build both maps from the **same** database, record the numbers that can be checked mechanically, and hand the side-by-side comparison to the user. **Execution stops at the end of this task.** Task 11 deletes the Folium path and must not start without the user's go-ahead.

**Files:**
- Create: `docs/superpowers/parity-2026-09-21.md` (the report; leave it uncommitted unless the user asks)

- [ ] **Step 1: Build both from the same database**

```bash
uv run python scripts/rebuild_map.py --skip-ingest --folium   # artifacts + www/index.html, same DB
cd frontend && npm run build && cd ..
```

- [ ] **Step 2: Record the mechanically comparable numbers**

```bash
uv run python - <<'EOF'
import json, re
from pathlib import Path
folium = Path("www/index.html").read_text()
fm = json.load(open("www/index_marker_metadata.json"))
art = Path("frontend/dist/data")
markers = json.load(open(art / "marker_metadata.json"))["markers"]
fc = json.load(open(art / "filter_config.json"))
print("markers           folium", len(fm), "| vite", sum(1 for m in markers if m["lat"] is not None))
for t in ("building", "block", "owner", "neighbourhood"):
    print(f"{t:17} rows folium", len(re.findall(f'data-type="{t}"', folium)), "| vite: count in the browser (Step 3)")
print("dataset_totals   ", fc["dataset_totals"])
print("index.html bytes  folium", Path("www/index.html").stat().st_size, "| vite", Path("frontend/dist/index.html").stat().st_size)
import gzip
gz = lambda f: len(gzip.compress(f.read_bytes(), 6))
folium_files = [Path("www/index.html")] + sorted(Path("www").glob("index_*.json"))
vite_files = [f for f in Path("frontend/dist").rglob("*") if f.is_file()]
print(f"total transfer    folium {sum(map(gz, folium_files)) / 1e6:.2f} MB gz"
      f" | vite {sum(map(gz, vite_files)) / 1e6:.2f} MB gz (page + code + artifacts)")
EOF
```

Paste the output into the report.

- [ ] **Step 3: Write the report and stop**

Create `docs/superpowers/parity-2026-09-21.md` containing the Step 2 output and this checklist, for the user to fill in by viewing `www/index.html` and `cd frontend && npm run preview` side by side:

```markdown
# Vite vs Folium parity — 2026-09-21

Both built from the same database. Folium: `www/index.html`. Vite: `cd frontend && npm run preview`.

## Numbers
<Step 2 output>

Row counts in the Vite build (browser console):
`['buildings','blocks','landlords','neighbourhoods'].map(t => [t, document.querySelectorAll('#'+t+'-table tbody tr').length])`

## Checklist (✅ / ❌ + note)
- [ ] Initial view fits the same bounds; basemap and label layer; attribution
- [ ] Markers: pink vs grey fill, sizes, SRO blue / co-op orange rings, dual building shows both
- [ ] Blocks: green ramp and empty blocks transparent (spec §11: check the ramp by eye)
- [ ] Block click-popup fields — *intentional:* median year shows 1965, not 1,965 (D10)
- [ ] Neighbourhood outlines; labels — *expected:* small position shifts (geo_point_2d vs centroid, D9)
- [ ] Legend: block ticks and note, VTU and housing keys, placed right of the sidebar
- [ ] Sidebar tabs: row counts match; header sorting; row hover highlights; selection checkboxes; footer totals
- [ ] Filters: sliders (currency labels show one `$`), neighbourhood tags with counts, select all / clear, search, hide empty blocks, colour and layer toggles, reset
- [ ] Status bar: totals (5,128 buildings) and in-view counts on pan/zoom
- [ ] CSV export of visible buildings — *expected:* Folium's 18 columns first, in Folium's order, then 23 more (`lat`/`lon`, portfolio, co-op/SRO/rezoning detail); no internal columns
- [ ] Building popups (spec §7 redesign, not parity): check the 11 migrated fields on a co-op, an SRO, a portfolio building and an overlay-only record
- [ ] Page weight / load time (see "total transfer" above); no console errors
```

Then **stop and tell the user**. Point them to the report and the two commands, and wait for their go-ahead before Task 11.

---

> ## ⛔ STOP — do not start Task 11 until the user has compared the builds and says to continue.

---

### Task 11: Delete `sica_mapping` and the Folium path

Spec §9 step 7. Runs only after the user signs off on Task 10.

**Files:**
- Delete: `src/sica_mapping/` (whole package, including `data/tables.py` per D5), `build_sica_map.py`, `scripts/validate_migration.py`, `scripts/build_vtu_public_extract.py`
- Modify: `pyproject.toml` (drop `folium`, `loguru`), `uv.lock`
- Modify: `config.toml` (drop `vtu` key and `[options]` table)
- Modify: `src/sica_core/paths.py` (drop `vtu_public`; docstring), `src/sica_core/config.py` (the `vtu_raw` comment)
- Modify: `tests/test_data_layout.py` (drop the `vtu` mapping)
- Modify: `scripts/rebuild_map.py` (drop `--folium`)
- Modify: `README.md`, `data/README.md`, `docs/DATA_SOURCES.md`

- [ ] **Step 1: Confirm `build_vtu_public_extract.py` has no remaining consumer**

```bash
grep -rnE "vtu_membership_public|config\.vtu\b|vtu_public" --include='*.py' --include='*.toml' \
     src/sica_core scripts tests config.toml | grep -v build_vtu_public_extract.py
```

Expected: only `config.toml`'s `vtu =` line, `paths.py`'s `vtu_public`, `config.py`'s comment and `test_data_layout.py`'s `"vtu"` mapping, all removed below. If anything else appears, stop and report it.

- [ ] **Step 2: Delete the package and scripts**

```bash
git rm -r src/sica_mapping build_sica_map.py scripts/validate_migration.py scripts/build_vtu_public_extract.py
```

- [ ] **Step 3: Drop `--folium` from `scripts/rebuild_map.py`**

Remove the `--folium` argument, its `if args.folium:` block, `LEGACY_CACHE_DIR`, the `export_to_cache` and `subprocess` imports, and the `--folium` paragraph and usage mention from the docstring.

- [ ] **Step 4: Retire the `vtu` key and `[options]`**

- `config.toml`: delete the `vtu = "data/derived/vtu_membership_public.csv"` line and the whole `[options]` table (`out`, `bbox`, `tiles`, `sidebar_width`, `verbose`). Their presentation values now live in `frontend/src/config.ts`.
- `src/sica_core/paths.py`: delete `self.vtu_public = ...`. In the module docstring, change "read by the ingest and by sica_mapping" to "read by the ingest and scripts/rebuild_map.py".
- `tests/test_data_layout.py`: delete `"vtu": "vtu_public",` from `CONFIG_KEYS`.
- `src/sica_core/config.py`: replace the comment above `_REQUIRED_PATHS` (the one explaining `vtu_raw` vs `sica_mapping`'s `vtu` key) with:

```python
# "vtu_raw" is the raw NationBuilder export (data/raw/nationbuilder/), allow-
# listed down to a few columns by ingest/membership.py.
```

- [ ] **Step 5: Drop the dependencies**

In `pyproject.toml`, remove `"folium",` and `"loguru",` from `dependencies`. Then:

```bash
uv lock
uv sync
```

- [ ] **Step 6: Confirm nothing imports `sica_mapping`**

```bash
grep -rnE "^\s*(from|import) sica_mapping|build_sica_map" --include='*.py' --include='*.toml' --include='*.yml' . \
     --exclude-dir=.venv --exclude-dir=.git --exclude-dir=.uv-cache --exclude-dir=node_modules
```

Expected: only `.github/workflows/ci.yml` and `deploy.yml` (Task 13 fixes those). Docstring and comment mentions in `src/sica_core/` (e.g. "forked from src/sica_mapping/…") are provenance notes and stay (D15).

- [ ] **Step 7: Update the docs**

`data/README.md` rebuild order: delete the `scripts/build_vtu_public_extract.py` line, and add after the `rebuild_map.py` line:

```
cd frontend && npm ci && npm run build                          # frontend/dist (see frontend/README.md)
```

`README.md`, section by section:
- **Intro + Highlights (lines 1–19):** replace with two paragraphs. SICA Mapping has two halves: `sica_core`, a Python data package that ingests sources into SQLite and exports a versioned artifact directory; and `frontend/`, a Vite + TypeScript map that reads only that directory. Link spec §3.
- **Repository Layout table:** replace the `build_sica_map.py`, `src/sica_mapping/*` and `www/` rows with `src/sica_core/` (ingest, overlays, export), `scripts/rebuild_map.py` (ingest + export), `frontend/` (the map; see `frontend/README.md`) and `data/derived/artifacts/` (the contract between them, gitignored).
- **Requirements:** Python 3.12+ and `uv` for the backend; Node 24 (`frontend/.nvmrc`) for the frontend. Each half needs only its own toolchain. Drop `folium` and `loguru` from the list.
- **Installation:** keep the `uv sync` block; drop the `sica_mapping` tip; add `cd frontend && npm ci`.
- **Input Data Expectations:** delete the `--vtu` row (its extract is retired).
- **Running the Map Builder, CLI Reference, Output, Pipeline Stages, Frontend Rendering:** replace all five sections with one short "Building the map" section. It gives the rebuild order from `data/README.md`, then `npm run dev` / `npm run build`, and points to `frontend/README.md`.
- **Development Workflow:** replace the `build_sica_map.py`, `--stage` and `src/sica_mapping/frontend/` bullets with: `rebuild_map.py [--skip-ingest]` when data or export logic changes; `npm run dev` (hot reload) for everything in `frontend/`; `uv run pytest` and `npm test` for the two test suites.
- **Branching & Deployment:** leave for Task 13.

`docs/DATA_SOURCES.md`: in the summary table's "Consumed by" column (lines 54–63), and in each source's **Consumed by:** line (lines ~136, 161, 185, 204, 225, 275, 308, 351, 439), drop `sica_mapping`. The overlay sources (`sra_housing_combined.csv`, `rezoning_applications.csv`, `coops_vancouver.csv`) are now ingested and matched by `sica_core` (`ingest/overlays.py`). Say so where the old line said "`sica_mapping` only (`overlays.py`)". Mark `local-area-boundary.csv` as "no longer consumed (`sica_core` uses the GeoJSON export)". Update the prose references to `src/sica_mapping/data/overlays.py` (lines ~120, 220, 268) to `src/sica_core/ingest/overlays.py`.

- [ ] **Step 8: Run both suites**

Run: `uv run pytest -q`, then `cd frontend && npm test && npm run typecheck && npm run build`
Expected: Python 64 passed (no test removed; one mapping entry dropped); frontend 43 passed; build succeeds.

- [ ] **Step 9: Commit** *(ask first)*

```bash
git add pyproject.toml uv.lock config.toml src/sica_core/paths.py src/sica_core/config.py \
        tests/test_data_layout.py scripts/rebuild_map.py README.md data/README.md docs/DATA_SOURCES.md
git commit -m "Delete sica_mapping and the Folium build; the map is frontend/"
```

(The `git rm` from Step 2 is already staged.)

`www/` and `.preprocessed/` may still exist locally as gitignored build output. Mention them to the user; don't delete them.

---

### Task 12: Synthetic artifact fixtures

Spec §11 and D13. CI cannot run ingest (`data/` is gitignored), so the frontend job builds against a small committed artifact set. It is *generated* through `export_artifacts()` from an invented in-memory database, so it can't drift from the real contract. A pytest guard regenerates it and compares bytes.

**Files:**
- Create: `scripts/make_frontend_fixtures.py`
- Create: `frontend/fixtures/` (five generated files, committed)
- Test: `tests/test_frontend_fixtures.py`

**Interfaces:**
- Produces: `uv run python scripts/make_frontend_fixtures.py [--out DIR]` (default `frontend/fixtures`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frontend_fixtures.py
"""frontend/fixtures/ is generated, never hand-edited: regenerating it must
reproduce the committed files byte for byte, and it must hold no membership."""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "frontend" / "fixtures"
FILES = [
    "filter_config.json", "marker_metadata.json", "building_records.json",
    "blocks.geojson", "local-area-boundary.geojson",
]


def test_committed_fixtures_match_the_generator(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/make_frontend_fixtures.py", "--out", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in FILES:
        assert (tmp_path / name).read_bytes() == (FIXTURES / name).read_bytes(), (
            f"{name} drifted — regenerate: uv run python scripts/make_frontend_fixtures.py"
        )


def test_fixtures_hold_no_membership():
    markers = json.loads((FIXTURES / "marker_metadata.json").read_text())["markers"]
    assert markers and all(m["member_count"] == 0 and m["is_vtu"] is False for m in markers)
    totals = json.loads((FIXTURES / "filter_config.json").read_text())["dataset_totals"]
    assert totals["members"] == 0 and totals["vtu_buildings"] == 0


def test_fixtures_cover_every_source_and_carry_the_contract_version():
    markers = json.loads((FIXTURES / "marker_metadata.json").read_text())["markers"]
    assert {m["source"] for m in markers} == {"building", "overlay_sro", "overlay_coop"}
    for name in FILES[:4]:
        assert json.loads((FIXTURES / name).read_text())["schema_version"] == 1, name
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_frontend_fixtures.py -v`
Expected: FAIL. The script doesn't exist (non-zero exit), and `frontend/fixtures/` is missing (`FileNotFoundError`).

- [ ] **Step 3: Write `scripts/make_frontend_fixtures.py`**

```python
#!/usr/bin/env python3
"""Generate frontend/fixtures/: a tiny, entirely invented artifact set.

The frontend CI job builds against it (data/ is gitignored, so CI cannot run
ingest). It is produced by the real export_artifacts() from an in-memory
database, so its shape is the real contract, not a hand-written copy. It
proves the build and the contract shape, not the data.

Invented only: no real addresses, owners or membership (vtu_membership stays
empty). Deterministic: fixed timestamps, so regenerating reproduces the
committed bytes — tests/test_frontend_fixtures.py checks that.

Usage: uv run python scripts/make_frontend_fixtures.py [--out frontend/fixtures]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sica_core.db import init_db  # noqa: E402
from sica_core.export import export_artifacts  # noqa: E402

NOW = pd.Timestamp("2026-01-01", tz="UTC")
TS = "2026-01-01T00:00:00+00:00"


def _square(lon: float, lat: float, size: float = 0.002) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[lon, lat], [lon + size, lat], [lon + size, lat + size],
                         [lon, lat + size], [lon, lat]]],
    }


# (id, addr_key, address, area, lat, lon, units, year, land, bldg, ratio,
#  issues, landlord, block, is_coop, is_sro, coop_status, coop_model, coop_url, housing_name)
BUILDINGS = [
    (1, "100 example st", "100 Example St", "Northside", 49.281, -123.129, 40, 1965,
     5000000, 800000, 0.16, 0, 1, 1, 0, 0, None, None, None, None),
    (2, "110 example st", "110 Example St", "Northside", 49.2812, -123.1288, 12, 1978,
     2500000, 400000, 0.16, 1, 1, 1, 1, 0, "Active", "Leasehold", "https://example.org/coop",
     "Example Co-op"),
    (3, "200 sample ave", "200 Sample Ave", "Southside", 49.271, -123.119, 80, 1972,
     9000000, 1500000, 0.17, 0, 2, 2, 0, 1, None, None, None, "Sample Rooms"),
    (4, "210 sample ave", "210 Sample Ave", "Southside", 49.2712, -123.1188, None, None,
     None, None, None, 0, 2, 2, 0, 0, None, None, None, None),
]


def _seed(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO landlords (landlord_id, display_name, owner_key, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [(1, "Example Holdings Ltd", "example-holdings-ltd", TS, TS),
         (2, "Sample Rentals Inc", "sample-rentals-inc", TS, TS)],
    )
    conn.executemany(
        "INSERT INTO blocks (block_id, geom, ingested_at) VALUES (?, ?, ?)",
        [(1, json.dumps(_square(-123.130, 49.280)), TS),
         (2, json.dumps(_square(-123.120, 49.270)), TS),
         (3, json.dumps(_square(-123.110, 49.260)), TS)],  # empty block
    )
    for (bid, key, addr, area, lat, lon, units, year, land, bldg, ratio, issues, landlord,
         block, coop, sro, cstatus, cmodel, curl, hname) in BUILDINGS:
        conn.execute(
            "INSERT INTO buildings (building_id, addr_key, address, local_area, lat, lon, units, "
            "year_built, value_land, value_bldg, bldg_land_ratio, n_issues, landlord_id, block_id, "
            "is_coop, is_sro, coop_status, coop_ownership_model, coop_url, housing_name, sro_owner, "
            "sro_operator, sro_occupancy_status, sro_registered_rooms, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (bid, key, addr, area, lat, lon, units, year, land, bldg, ratio, issues, landlord,
             block, coop, sro, cstatus, cmodel, curl, hname,
             "Sample Owner" if sro else None, "Sample Operator" if sro else None,
             "Open" if sro else None, "24" if sro else None, TS, TS),
        )
    conn.executemany(
        "INSERT INTO overlay_housing (addr_key, address, housing_name, local_area, lat, lon, "
        "is_coop, is_sro, sro_owner, sro_operator, sro_occupancy_status, sro_registered_rooms, "
        "coop_status, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [("300 invented rd", "300 Invented Rd", "Invented Rooms", "Southside", 49.265, -123.105,
          0, 1, "Invented Owner", "Invented Operator", "Open", "10", None, TS),
         ("400 madeup way", "400 Madeup Way", "Madeup Co-op", "Northside", 49.285, -123.135,
          1, 0, None, None, None, None, "Active", TS)],
    )
    conn.commit()


BOUNDARY = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature",
         "properties": {"name": "Northside", "geo_point_2d": {"lon": -123.130, "lat": 49.283}},
         "geometry": _square(-123.140, 49.275, 0.02)},
        {"type": "Feature",
         "properties": {"name": "Southside", "geo_point_2d": {"lon": -123.115, "lat": 49.265}},
         "geometry": _square(-123.125, 49.255, 0.02)},
    ],
}


def build(out_dir: Path) -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed(conn)
    with tempfile.TemporaryDirectory() as tmp:
        boundary = Path(tmp) / "local-area-boundary.geojson"
        boundary.write_text(json.dumps(BOUNDARY), encoding="utf-8")
        export_artifacts(conn, out_dir, boundary_geojson_path=str(boundary), now=NOW)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(REPO_ROOT / "frontend" / "fixtures"))
    args = parser.parse_args()
    build(Path(args.out))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the fixtures, then run the tests**

```bash
uv run python scripts/make_frontend_fixtures.py
ls -la frontend/fixtures
uv run pytest tests/test_frontend_fixtures.py -v
```

Expected: five files (~17 KB total); 3 passed.

- [ ] **Step 5: Build the frontend against them**

```bash
cd frontend && SICA_ARTIFACTS_DIR=fixtures npm run build && ls dist/data && cd ..
```

Expected: the build succeeds and `dist/data/` holds the five fixture files.

- [ ] **Step 6: Run the full Python suite**

Run: `uv run pytest -q`
Expected: 67 passed (64 + 3).

- [ ] **Step 7: Commit** *(ask first)*

```bash
git add scripts/make_frontend_fixtures.py frontend/fixtures tests/test_frontend_fixtures.py
git commit -m "Add generated synthetic artifact fixtures for the frontend build"
```

---

### Task 13: Split CI into backend and frontend jobs; disable deploy's push trigger

Spec §11. Deploy stays undecided: **no deploy path is built.** Per D12, `deploy.yml` loses its push trigger, and a manual run fails immediately with a pointer to the spec.

**Files:**
- Rewrite: `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`
- Modify: `README.md` (Branching & Deployment section)

- [ ] **Step 1: Rewrite `ci.yml`**

```yaml
# .github/workflows/ci.yml
# The promotion gate: nothing reaches `main` (and therefore nothing can be
# promoted to `production`) without both jobs passing.
#
# backend  — sica_core: ruff (advisory until the existing findings are
#            cleaned up) and pytest.
# frontend — frontend/: type check, unit tests, and a production build
#            against frontend/fixtures/ (generated, invented data; CI cannot
#            run ingest because data/ is gitignored). It proves the build and
#            the artifact contract, not the data.
name: CI

on:
  pull_request:
    branches: [main, production]
  push:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"

      - name: Sync dependencies
        run: uv sync --group dev || uv sync

      - name: Ruff lint (advisory)
        continue-on-error: true
        run: uv run ruff check .

      - name: Ruff format check (advisory)
        continue-on-error: true
        run: uv run ruff format --check .

      - name: Tests
        run: uv run pytest -q

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version-file: frontend/.nvmrc
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install
        run: npm ci

      - name: Type check
        run: npm run typecheck

      - name: Unit tests
        run: npm test

      - name: Build against the synthetic fixtures
        env:
          SICA_ARTIFACTS_DIR: fixtures
        run: |
          npm run build
          test -f dist/index.html
          test -f dist/data/marker_metadata.json
```

- [ ] **Step 2: Rewrite `deploy.yml`**

```yaml
# .github/workflows/deploy.yml
name: Deploy map to GitHub Pages

# DISABLED. How deploy gets *real* artifacts is an open decision — see
# docs/superpowers/specs/2026-09-19-renderer-rewrite-design.md §11. CI cannot
# produce them (data/ is gitignored), and committing them would republish
# per-building membership until the §12 public export profile exists.
#
# The push trigger is removed. A manual run fails immediately with this
# pointer rather than calling the deleted Folium build. Nothing here builds
# or deploys; restore a real job once §11 is decided.
on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  disabled:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy is disabled pending a decision
        run: |
          echo "::error::Deploy is disabled — how it gets real artifacts is undecided (design spec §11)."
          exit 1
```

- [ ] **Step 3: Update README's Branching & Deployment section**

- The `production` row: replace "`.github/workflows/deploy.yml` builds and publishes to GitHub Pages on every push here" with "What should be live. Deploy is currently **disabled** (`deploy.yml` has no push trigger) until design spec §11 decides how it gets real artifacts."
- "Everyday work" step 2: replace the `build_sica_map.py` smoke-test sentence with "`.github/workflows/ci.yml` runs two jobs on the PR: **backend** (pytest; ruff advisory) and **frontend** (type check, unit tests, and a build against `frontend/fixtures/`)."
- "Releasing": prefix with "*Paused while deploy is disabled (spec §11).*" and leave the steps as the intended process.
- "One-time GitHub setup": replace "require the `CI` check to pass" (both bullets) with "require the `backend` and `frontend` checks to pass".
- "Notes": delete the pure-CSV-path bullet and the `--local-area` bullet (both describe the deleted build).

- [ ] **Step 4: Validate the workflow files**

```bash
uv run python -c "import yaml, sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]; print('valid YAML')" \
  .github/workflows/ci.yml .github/workflows/deploy.yml
grep -n "build_sica_map" .github/workflows/*.yml README.md || echo "no references left"
```

Expected: `valid YAML`, then `no references left`. If PyYAML is not importable, run `uv run --with pyyaml python -c ...` instead.

- [ ] **Step 5: Commit** *(ask first)*

```bash
git add .github/workflows/ci.yml .github/workflows/deploy.yml README.md
git commit -m "Split CI into backend and frontend jobs; disable deploy's push trigger"
```

- [ ] **Step 6: Tell the user about branch protection**

Renaming the CI job from `check` to `backend` and `frontend` changes the status-check names. If branch protection on `main` or `production` requires the old `check`, PRs will wait forever for a check that never reports. A repo admin must update the required checks (Settings → Branches) to `backend` and `frontend`. This is the user's action; do not attempt it.

---

## Done when

- `npm run build` in `frontend/` produces a working map from the artifact directory alone, and the user has signed off on the Task 10 parity report.
- `sica_mapping`, `build_sica_map.py`, `validate_migration.py` and `build_vtu_public_extract.py` are gone. `folium` and `loguru` are dropped. `config.toml` has no `[options]` and no `vtu` key.
- `scripts/rebuild_map.py` is ingest + export only.
- CI runs a backend job and a frontend job, the frontend job building against generated fixtures. `deploy.yml` no longer runs on push.
- Python: 67 passed. Frontend: 43 passed; `tsc --noEmit` clean.
- Artifact transfer about 2 MB gzipped (coordinates rounded to 6 decimals), against the Folium page's ~4.2 MB.

## Carried forward, not in this plan

- How deploy gets real artifacts (spec §11). Blocked on the public export profile (spec §12).
- The membership-exposure step (spec §12).
- The previous plan's remaining minors (dropped or deferred by its review): the matcher's unused rezoning `unmatched_records`, and '' vs null for empty overlay text fields (documented on `BuildingRecord`).
- `config.toml`'s `local_area_boundary` (CSV) key becomes unused after Task 11. The fetcher still downloads the CSV. It's harmless; retire it separately.
- Converting `wiring.js` to TypeScript, and formal JSON Schemas for the artifacts (spec §2 non-goals).
