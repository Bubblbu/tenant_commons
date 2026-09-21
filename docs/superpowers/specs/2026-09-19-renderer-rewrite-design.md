# Renderer rewrite: Folium removal and a one-directional data contract

Design doc. Status: draft for review — revised 2026-09-21, see below.
Date: 2026-09-19

---

> **Revision 2026-09-21 — renderer target changed to a standalone Vite project.**
>
> The original draft replaced Folium with an *interim Python shell*
> (`sica_mapping/render.py` substituting options into `shell.html`), deferring
> Vite/TypeScript to a later port. That is reversed: the backend (`sica_core`)
> is now meant to grow as its own product feeding several frontends, and the
> map as its own project. An interim Python renderer would be new code written
> to be thrown away at that port.
>
> Instead, steps 4–8 build a `frontend/` Vite project directly and delete
> `sica_mapping` entirely. Scope stays the same size: the Vite scaffold replaces
> `render.py`, not adds to it, and `wiring.js` moves in as JavaScript —
> converting it to TypeScript is still out of scope.
>
> **Unaffected:** §4 (data contract), §5 (overlay port), §7 (popup redesign),
> §8 (verification), §12 (membership). Steps 1–3 and the
> `2026-09-20-overlay-port-and-data-contract` plan stand as written.
>
> **Changed:** §2, §3, §6, §9 (steps 4–8), §10, §11, §13.

---

## 1. Context

`sica_core` owns the data pipeline; `sica_mapping` owns the map. That is the
intended split, and it is not what the code does today.

`build_map()` loads `.preprocessed/*.json` from `sica_core`, and then keeps
doing data work:

- reads `local-area-boundary.csv` from the raw Open Data path at render time
  (`build.py:243`)
- calls `match_overlays()`, which opens the co-op, SRO, rezoning and buildings
  **CSVs**, performs address matching and point-in-polygon lookups, and *adds
  rows* to `pts_df` (`build.py:246`)
- builds four HTML tables — 12,026 `<tr>` strings — in Python
- writes the three `www/index_*.json` files the frontend actually consumes
  (`build.py:318-341`), derived from the post-overlay frame

The last point is the structural problem. The real frontend data contract is
manufactured two-thirds of the way through a Folium render, after the renderer
has mutated the data. `.preprocessed/` is not the boundary it appears to be,
and `sica_core` is not currently the source of truth for what the map shows.

The overlay duplication makes this concrete: `sica_core` ingests `raw_sro`,
`raw_coops` and `raw_rezoning` into SQLite, and the renderer then ignores those
tables and re-derives the same matching from CSVs.

### Measured cost

`www/index.html` is 22.16 MB (3.78 MB gzipped), composed of:

| Slice | Size | Share |
|---|---|---|
| 23 inline GeoJSON payloads (blocks layer alone: 9.8 MB) | 9.39 MB | 42.4% |
| 12,026 pre-rendered sidebar `<tr>` rows | 6.59 MB | 29.7% |
| 5,282 marker + popup constructions | 4.76 MB | 21.5% |

Folium's only remaining contributions are the base map, the baked markers, and
four layer globals. `wiring.js` — 1,927 lines — is already framework-free
vanilla JS that fetches its own data at runtime. It touches Folium in exactly
six lines: four `window["$layer_var"]` lookups (`wiring.js:41-44`) and two
`window[marker_var]` lookups (`wiring.js:444`, `:481`).

The map is already a hand-written Leaflet app. This work finishes that.

## 2. Goals and non-goals

**Goals**

1. `sica_core` becomes the sole producer of every value the map displays.
2. The frontend data contract becomes an explicit, versioned artifact set.
3. Python stops emitting markup and stops reading CSVs at render time.
4. Folium is removed as a dependency.
5. The map becomes a standalone `frontend/` Vite project (CLAUDE.md §5) whose
   only input is the artifact set. `sica_mapping` is deleted; Python emits no
   HTML, CSS or JS at all.

**Non-goals**

- Converting `wiring.js` to TypeScript. It moves into the Vite project as
  JavaScript (with `allowJs`), patched only as §6 describes. The project is
  TypeScript-ready — `bootstrap.ts` and anything new is written in TS — so
  conversion can proceed module by module afterwards.
- A JSON Schema for each artifact and TS types generated from it. The
  `schema_version` field (§4) is the only contract enforcement here; formal
  schemas are the natural follow-on once the artifacts stop changing shape.
- Frontend feature work beyond parity plus the §7 popup: no framework, no
  marker clustering, no new filters.
- Public/sensitive field filtering (CLAUDE.md §3). Out of scope here, but this
  work is a prerequisite: afterwards there is exactly one function producing the
  frontend's JSON, so the filter has one place to live instead of two. See §12
  for a finding that should drive that work.
- Sidebar row virtualization. The 12,026-row DOM cost is real but separable.
- Interaction performance. Markers already render to canvas
  (`prefer_canvas=True`). This work improves load time, not steady-state pan,
  zoom or filter response.

## 3. Target architecture

```
sica_core (Python)               artifacts/                  frontend/ (Vite)
(all data derivation)            (the contract)              (all presentation)

ingest → overlays → merge →      filter_config.json          index.html
metrics → portfolios → export    marker_metadata.json        src/bootstrap.ts
                                 building_records.json       src/wiring.js
                                 blocks.geojson              sidebar/legend/popup
                                 local-area-boundary.geojson
```

Flow is one-directional. The frontend never opens a CSV, never touches SQLite,
never computes a derived *data* value. It does own all presentation: markup,
styling, colour scales, legend ticks, table rows, popups.

The artifact directory is the only thing the two sides share. `sica_core` does
not know where the frontend lives, and the frontend does not know how the
artifacts were made — a second frontend (a partner org's map, the internal
tool's export view) reads the same directory.

## 4. The data contract

`sica_core.export` gains one function producing the full artifact set, with a
declared schema and a `schema_version` field per file so the frontend
fails loudly on mismatch instead of rendering an empty map.

| Artifact | Shape | Change from today |
|---|---|---|
| `filter_config.json` | unchanged | now emitted by `sica_core`, not `build.py` |
| `marker_metadata.json` | `{schema_version, markers}`: per-building data records (as built, 2026-09-21; styling is computed by the frontend, plan 2 D3) | **gains `lat`/`lon`**; **drops `marker_var`** |
| `building_records.json` | `{columns, records}` | now from the buildings table unioned with `overlay_housing` (§5), not a post-overlay frame; **gains the 11 popup-only fields** (§7); `source` becomes a real discriminator; `columns` is an explicit public list (`export.BUILDING_RECORD_COLUMNS`, 41 columns), since the CSV export writes it verbatim |
| `blocks.geojson` | FeatureCollection | **new**; replaces the 9.8 MB inline payload |
| `local-area-boundary.geojson` | FeatureCollection | **copied from `raw/`** — see below |

**`marker_metadata.json` needs `lat`/`lon`.** Coordinates currently live only
inside the baked Folium markers; `marker_var` is the handle `wiring.js` uses to
reach them. The `buildings` table has both columns. Once the bootstrap
constructs markers itself and keys them by `b_id`, `marker_var` is dead and the
two lookup sites become direct references.

**Neighbourhoods are a passthrough, not a derived artifact.** The fetcher
already downloads `local-area-boundary.geojson`
(`fetch/cov_open_data.py:32`; 51 KB, 22 features). Verified: its
`properties.name` values match what the render path expects, same spelling.
`local_area_boundaries_feature_collection()` (`spatial.py:527`) reads the *CSV*,
parses `geom` with shapely, re-serializes via `poly_to_geojson`, and attaches
`name` — a pure round trip of a file already on disk. Replace the function with
a file copy.

**Blocks stay derived.** `blocks.geom` is already GeoJSON text in SQLite, so
`parse_geom` → `__geo_interface__` is a wasted round trip and the stored string
should be emitted directly. But `reconstruct_blocks()` (`export.py:201`) joins
eight properties the choropleth colors by — `buildings`, `total_units`,
`median_year_built`, `member_buildings`, `total_members`, `member_share`,
`local_area`, `block_label`. The Open Data GeoJSON export is the *input*, not
the artifact.

Not changing the fetcher's `block-outlines` format from CSV to GeoJSON: the CSV
already carries GeoJSON in its `geom` column, so the only gain is avoiding a
10 MB CSV parse, against the cost of rewriting `ingest/blocks.py`'s column
mapping.

Export no longer round-trips geometry through shapely. As built (2026-09-21) it
still uses shapely inside `reconstruct_blocks()`, for block-number local-area
resolution and block labels; moving those to ingest time would remove it from
export entirely, but nothing needs that now. Shapely remains in `sica_core` for
ingest-time work (overlay point-in-polygon, block spatial join).

## 5. The overlay port

The largest and riskiest piece. `match_overlays()` is 521 lines and currently
runs at render time, *adding rows* to `pts_df` — SRO and co-op records with no
matching building become synthetic housing entries.

Ported into `sica_core` as an ingest-time step, writing into the buildings layer
so the export sees the rows naturally. All inputs are already in SQLite:

| Current input | Replacement |
|---|---|
| `coops_path` CSV | `raw_coops` |
| `sro_path` CSV | `raw_sro` |
| `rezoning_path` CSV | `raw_rezoning` |
| `buildings_path` CSV (for `secondary_addresses`) | `raw_buildings.secondary_addresses` — confirmed present |
| `local_area_boundary_fc` | `local-area-boundary.geojson` from `raw/` |

The logic that must survive unchanged: the loose-key address index, the
direction / range / unit-prefix regex variants (`_address_key_variants`), the
secondary-address fallback, and `_resolve_local_area`'s point-in-polygon lookup
for records with no building match.

### Where synthetic rows live

`_append_extra_housing()` currently concatenates SRO and co-op records that
matched no building onto the buildings frame. Today that is **153 rows**
(b_id 5129-5281: 117 SRO, 36 co-op), carrying only `address`, `local_area`,
`lat`/`lon` and a housing type — no units, year built, assessed values,
`block_id` or owner.

These go in a **companion `overlay_housing` table**, unioned in at export time,
not appended to `buildings`. Rationale:

- They are a matching *failure* artifact — records whose address key matched
  nothing. Merging them into `buildings` bakes that failure into the canonical
  table.
- Their count is a data-quality metric. 153 today; if a refresh pushes it to
  400, that is a visible signal the matcher regressed. Merged in, it is
  invisible.
- Correctness by default: `SELECT COUNT(*) FROM buildings`, per-neighbourhood
  counts and any average over `buildings` stay right without remembering to
  filter. This is the kind of footgun that survives a refactor and quietly
  corrupts a funder-facing number.
- Their schema genuinely differs — five populated fields against seventeen.

No map behaviour changes either way: these rows already have `block_id` NULL,
so block aggregation already excludes them.

### Required fix: the `source` column is fake

`tables.py:33` sets `tbl["source"] = "building"` unconditionally. It is a
hardcoded constant, not a provenance marker, so all 5,281 rows in
`index_building_records.json` claim `source: "building"` and the 153 synthetic
rows are **indistinguishable from real buildings** in the public export — 153
buildings with no owner, no units and no assessed value, nothing marking them as
unmatched source records. Anyone consuming that JSON (a partner org, a funder)
gets them as real.

The export must emit a real discriminator: `building` for rows from `buildings`,
`overlay_sro` / `overlay_coop` for rows unioned from `overlay_housing`.

## 6. File layout after

```
src/sica_core/
  ingest/overlays.py       ← ported from sica_mapping/data/overlays.py
  export.py                ← emits the artifact set
  geometry.py              ← parse_geom retained (ingest only)

src/sica_mapping/          ← deleted

frontend/                  ← new; its own package.json, no Python
  package.json             ← vite, typescript, leaflet
  vite.config.ts           ← serves/copies the artifact dir at /data/
  tsconfig.json            ← strict, allowJs
  index.html               ← from sidebar.html + legend_*.html, placeholders removed
  src/
    config.ts              ← tile presets, sidebar width, artifact base URL
    bootstrap.ts           ← new: map, markers, GeoJSON layers, hand-off
    wiring.js              ← moved; 6 Folium lines + 3 URL placeholders patched
    blocks.ts              ← block style + greens scale, from layout.py/colors.py
    legend.ts              ← neighbourhood tags + block ticks, from layout.py
    tables.ts              ← sidebar rows, from tables.py
    popup.ts               ← §7 redesign, one escape helper
  README.md                ← dev/build commands, artifact dir contract
```

Accounting, so the plan can be checked against reality as it lands:

| Change | Lines |
|---|---|
| `data/` removed wholesale — `pipeline.py` (558), `spatial.py` (610), `vtu.py` (178), `tables.py` (239), `geometry.py` (36), `__init__.py` (77) | −1,698 |
| `data/overlays.py` — **moves** to `sica_core`, not deleted | −521 |
| `cli.py` | −207 |
| `build.py` | −363 |
| `frontend/layout.py` (410) + `colors.py` (18) — Folium emission deleted; presentation logic (block style, legend markup, popup) reimplemented in TS | −428 |
| `core/` — `logging.py`, `io.py`, `normalization.py`, `__init__.py` | −307 |
| `__init__.py` — package root (10) + `frontend/` (21) | −31 |
| **Python removed** (521 of it relocated, not deleted) | **−3,555** |
| `frontend/templates/` — `wiring.js` (1,927) + three HTML fragments (819) **move** to `frontend/` | 2,746 moved |
| **`sica_mapping` remaining** | **0** (from 6,301 incl. templates) |

Outside the package: `build_sica_map.py` (12) and
`scripts/validate_migration.py` (178) are deleted.
`scripts/build_vtu_public_extract.py` imports `sica_mapping.core` and
`sica_mapping.data`, and its output (`config.toml`'s `vtu` key,
`derived/vtu_membership_public.csv`) is read only by the deleted CSV pipeline —
`sica_core` ingests `vtu_raw`. Confirm no other consumer, then retire the script
and the `vtu` key with it.

**`cli.py`, `build_sica_map.py` and `build.py` go, with no Python replacement.**
Of the 15 args `build_map()` consumes, nine exist only to feed
`run_data_pipeline()` and `match_overlays()`: `addresses`, `blocks`,
`block_numbers`, `buildings`, `vtu`, `local_area_boundary`, `local_area`,
`bbox`, `stage`. Of the rest, `tiles` and `sidebar_width` are presentation and
move to `frontend/src/config.ts` (the tile presets in `build.py:43-90`, incl.
the Esri attribution, move with them); `out`, `data_dir` and `verbose` have
nothing left to configure. `config.toml`'s `[options]` table goes.

**`scripts/rebuild_map.py` becomes backend-only:** ingest, then
`export_artifacts()` into an artifact directory — a new `config.toml`
`[paths]` key, `artifacts = "data/derived/artifacts"` (gitignored with the rest
of `data/`). It no longer renders anything. It gains `--skip-ingest`, so export
changes don't pay the ~19s ingest every time.

**The frontend finds the artifacts by a single setting.** `vite.config.ts` reads
`SICA_ARTIFACTS_DIR` (default `../data/derived/artifacts`) and serves it at
`/data/` under `npm run dev`, and copies it into `dist/data/` under
`npm run build`. The mechanism — a small inline plugin or
`vite-plugin-static-copy` — is the plan's choice. A different frontend, or a
partner's copy of this one, points the same variable elsewhere.

**Dev loop.** `uv run python scripts/rebuild_map.py` when data changes;
`npm run dev` in `frontend/` for everything else, with hot reload. Neither side
needs the other's toolchain to iterate on its own half.

**Leaflet comes from npm**, not the CDN tags Folium injected, so its version is
pinned in `package-lock.json`. `wiring.js` uses Leaflet through the global `L`
today; `bootstrap.ts` imports `leaflet` and assigns `window.L` once, so
`wiring.js` needs no import rewrite.

**`bootstrap.ts`** is the only genuinely new logic: create the map, fetch the
artifacts, construct markers from `marker_metadata.json` keyed by `b_id`, build
the two GeoJSON layers, expose the four handles `wiring.js` reads, hand off.
Marker styling (`base_radius`, `base_color`, `stroke_color`, `stroke_weight`,
`extra_rings`) was baked into Folium's metadata; the artifacts carry only data,
so styling is presentation computed by the frontend (`markers.ts`, plan 2 D3).

**Presentation logic moves from Python to TS, not data logic.** Three pieces of
`layout.py` compute from artifact values at render time and have to be
reimplemented: the block choropleth style (`greens_color` over
`total_units / max_total_units`, transparent for empty blocks), the
neighbourhood filter tags (from `filter_config.neighbourhoods`), and the block
legend's six ticks (from `filter_config.blocks_total_units_max`). All three
already read only artifact fields, so they belong on the frontend side of the
line — this is the §3 rule, not an exception to it. The `$placeholder` slots
they fill in `sidebar.html`, `legend_*.html` and `wiring.js:5-7,41-44` become
DOM writes or imports.

**Popups bind lazily on click** and are redesigned — see §7.

## 7. Popup redesign

### Why it moves

The popup is built today by string concatenation in `layout.py:173-255` and
baked into `index.html` 5,282 times. Eleven fields exist **only** inside that
string:

`housing_name`, `portfolio_name`, `portfolio_building_count`,
`portfolio_entities`, `coop_status`, `coop_ownership_model`, `coop_url`,
`sro_owner`, `sro_operator`, `sro_occupancy_status`, `sro_registered_rooms`

Because they are markup rather than data, they cannot be filtered, sorted,
exported or shown in the table. Meanwhile `building_records.json` carries
assessed values and membership history the popup never shows. The same building
therefore has three partial, overlapping representations — baked popup,
`building_records.json`, `marker_metadata.json`.

Binding popups lazily from `building_records.json` collapses that to one record
per building, serving the popup, the table and the filters alike. Removing
1.5 MB of baked HTML is a side effect, not the reason. Two further benefits:
popup changes become edit-and-reload instead of a ~19s ingest-and-render cycle,
and the scattered `escape()` calls collapse into one helper.

Cost: `building_records.json` grows by those 11 fields, and escaping becomes the
frontend's responsibility — it must use `textContent` or a single escape helper,
not string concatenation.

### Structure

Today's popup is flat: a bold address, an optional name line, five unlabelled
facts, then three blocks appended with `<br>`. The redesign groups them into
conditional sections, present only when the data is, and **leads with the
ownership story** — the project's differentiator per CLAUDE.md §1, currently
buried on line four and again at the bottom.

```
┌─ 1234 Davie St ──────────────┐
│ Hollyburn Properties         │   owner_group
│ Portfolio: 23 buildings,     │   portfolio_building_count
│   6 linked entities          │   portfolio_entities
├──────────────────────────────┤
│ 87 units · built 1974        │   units, year_built
│ West End                     │   local_area
│ Assessed $20.1M land         │   value_land, value_bldg
├──────────────────────────────┤
│ Co-op · Active (leasehold)   │   coop_* (conditional)
│ SRO/SRA · Owner X · 42 rooms │   sro_*  (conditional)
└──────────────────────────────┘
```

Assessed values and `local_area` are new to the popup; they already exist in
`building_records.json` and were previously visible only in the table.

### Membership is not in the new popup

An editorial decision, not a privacy control — the redesign is organised around
ownership, and membership does not serve that story. It is **not** a fix for the
exposure described in §12, and must not be described as one: membership data
remains in `marker_metadata.json`, `building_records.json`, `filter_config.json`
and the block choropleth, and marker colour still discloses it. Nothing else
changes on that axis in this work.

## 8. Verification

`scripts/validate_migration.py` is retired, not rewritten. It diffs against the
v1 CSV pipeline, which this work deletes; the backend has moved substantially
since v1 and the underlying data changes between refreshes, so an exact-match
harness against a moving dataset produces false alarms and stops being read.

Replaced by a throwaway fingerprint check scoped to the one risky step:

1. Before the port, dump a fingerprint of today's `match_overlays()` output —
   row counts by housing type, matched/unmatched counts, and a sorted
   `(addr_key, housing_type, local_area)` key set. **Key on `addr_key`, not
   `b_id`** — synthetic rows currently get `b_id = max + 1` assigned at render
   time (`_append_extra_housing`), and moving them into `overlay_housing`
   changes that assignment, so a `b_id`-keyed fingerprint would show a diff
   for every row regardless of whether the matching actually changed.
2. After the port, regenerate and diff against the frozen fixture.
3. Delete once the port has landed.

Deliberately not a permanent test. The permanent targeted tests CLAUDE.md §6
calls for (sensitivity filtering, claims merge) are separate work.

Existing tests (26, currently passing) must stay green throughout.

## 9. Sequencing

Each step leaves the map working.

1. Freeze the overlay fingerprint fixture (§8).
2. Port overlays into `sica_core` ingest, writing unmatched records to
   `overlay_housing`; verify against the fixture.
3. Add `lat`/`lon` to marker metadata; emit `blocks.geojson`; copy the boundary
   file. Artifacts now complete, still rendered by Folium.
4. Scaffold `frontend/` (Vite, TS, Leaflet from npm, artifact dir at `/data/`);
   move `wiring.js` and the HTML fragments in; write `bootstrap.ts`; patch the
   six Folium lines and three URL placeholders in `wiring.js`; port the block
   style and legend logic. Point `rebuild_map.py` at `export_artifacts()` and
   the new `artifacts` path. `npm run dev` now renders the full map; the Folium
   build still works alongside it but is no longer the reference.
5. Move table-row generation to `tables.ts`; delete `tables.py`. Add the 11
   popup fields to `building_records.json` and build the redesigned popup (§7)
   in `popup.ts`.
6. Parity check: `npm run build` output against the last Folium `index.html`,
   by hand, per §11. Only after it passes does the Folium path go.
7. Delete `sica_mapping`, `build_sica_map.py`, `validate_migration.py` and
   (once confirmed unused) `build_vtu_public_extract.py`; drop `folium` from
   `pyproject.toml` and `[options]` from `config.toml`.
8. Update the CI and deploy workflows (see §11).

The first three steps leave "the map working" in the old sense — Folium renders
it. From step 4 on, it means `npm run dev` renders it; the Folium build is kept
runnable only until step 6's parity check, so there is always something to
compare against.

## 10. Decisions taken

Recorded so the reasoning is not relitigated during implementation.

| Decision | Choice | Where |
|---|---|---|
| Renderer target | Standalone `frontend/` Vite project; `wiring.js` stays JS for now *(revised 2026-09-21 — was: interim Python shell)* | §6 |
| Repo layout | Monorepo: `frontend/` beside `src/sica_core/`; split repos only when a second org consumes the backend | §6 |
| Artifact location | `config.toml` `artifacts` path; frontend reads it via `SICA_ARTIFACTS_DIR`, served at `/data/` | §6 |
| Presentation logic (colour scale, legend ticks, table rows) | Frontend, in TS | §6 |
| Overlay matching | Moves into `sica_core` at ingest time | §5 |
| Synthetic overlay rows | Companion `overlay_housing` table, not merged into `buildings` | §5 |
| Neighbourhood boundaries | Passthrough of the already-fetched GeoJSON | §4 |
| Block outlines | Stay derived; fetcher keeps CSV | §4 |
| `cli.py` / `build_sica_map.py` | Deleted, no Python replacement; `rebuild_map.py` is ingest + export only *(revised 2026-09-21 — was: collapsed into `render()`)* | §6 |
| `validate_migration.py` | Retired, not rewritten | §8 |
| Popups | Lazy, rebuilt from `building_records.json`, restructured | §7 |
| Popup emphasis | Ownership story leads | §7 |
| Membership exposure | Deferred to its own step; nothing changes here | §12 |

One open decision: how deploy gets artifacts (§11). It does not block steps
4–7.

## 11. Risks

- **Overlay drift** is the main one. 521 lines of address-matching heuristics,
  relocated. Mitigated by §8, and by porting it first and separately, while the
  rest of the pipeline is unchanged.
- **CI and deploy are already broken** and this work must fix them. Both
  workflows run `build_sica_map.py` with no `--stage`, defaulting to `frontend`
  (`cli.py:17`); `.preprocessed/` is gitignored, so `cached_data_exists()` is
  false and they fall through to `run_data_pipeline` on `data/*.csv` — which
  commit `206990b` untracked. `ci.yml:52` still claims "committed data/*.csv
  only." This surfaces on first push of the local commits.

  After this work CI splits into two jobs: **backend** (`ruff`, `pytest`) and
  **frontend** (`npm ci`, `tsc --noEmit`, `npm run build`). The frontend job
  needs *some* artifact set to build against, and `data/` is gitignored, so CI
  cannot run ingest. Give it a small committed **synthetic fixture** set
  (`frontend/fixtures/`, a handful of invented buildings and blocks, correct
  `schema_version`, no real membership) — it proves the build and the contract
  shape, not the data.

  **Deploy is the open decision.** It needs *real* artifacts, which CI cannot
  produce. Two options:

  1. *Commit the public artifacts* and let deploy build the frontend from them.
     Only safe once the §12 public export profile exists — today every artifact
     carries per-building membership, and committing it would republish exactly
     what §12 says must not be public. (Membership data has leaked through this
     repo once before.)
  2. *Build locally, deploy the `dist/`* (e.g. `gh-pages` push or a
     manual-dispatch workflow taking an uploaded artifact) until then.

  Recommendation: option 2 now, move to option 1 when the §12 work lands.
  Either way, `deploy.yml` must not run on push until this is settled — disable
  its push trigger in step 8 rather than leave it failing.
- **`wiring.js` coupling beyond the known lines.** The grep covered
  `marker_var`, the four layer globals and the three URL placeholders; a full
  read of the file before step 4 is warranted, looking in particular for other
  `window.*` globals Folium defined and for DOM ids that `sidebar.html` /
  `legend_*.html` must keep.
- **Two toolchains.** The repo gains Node and `node_modules/` beside `uv`.
  Contributors touching only one half need only that half's toolchain; the
  README must say so. Pin the Node version (`.nvmrc` or `engines`) so CI and
  local agree.
- **Legend/colour-scale drift.** The block style and legend ticks are
  reimplemented rather than moved. Check the choropleth colours and tick labels
  against the Folium build by eye at step 6 — nothing automated would catch a
  subtly different green ramp.
- **Popup regressions.** The markup is reimplemented in JS *and* restructured at
  the same time (§7), so a diff against the old output will not be clean. The
  11 migrated fields are the ones to check by hand — they exist nowhere else
  today, so nothing else would catch their loss.

## 12. Finding: per-building membership exposure

Recorded here so the analysis is not lost. **Out of scope for this work** — it
is its own dedicated step.

CLAUDE.md §2 notes that the current site "exposes exact VTU membership counts
per building — sensitive to a landlord who finds the site." Measured against the
current export, that exposure is sharper than the wording suggests:

- **87 of 5,281 buildings** have any members at all
- **the maximum count is 2**

So the pink markers are not an aggregate signal. They are a map of 87 specific
buildings, nearly all with one or two members. Three consequences for whoever
picks this up:

1. **`is_vtu` alone discloses the full set.** Removing counts from the popup or
   the table while markers still render pink changes nothing.
2. **Banding is useless here.** There is nothing to band when every value is 1
   or 2.
3. **Block-level aggregation does not rescue it.** A block with one member
   building points straight back at that building.

The only effective version is dropping membership from the public export
entirely — neutral markers, no membership filters, no member-share choropleth —
with the full data retained in SQLite for the internal tool. That is a product
decision about what the public map is for, and it is the natural first task of
the CLAUDE.md §3 sensitivity work.

Membership appears in every public artifact today:

| Artifact | Fields |
|---|---|
| `marker_metadata.json` | `is_vtu`, `member_count` |
| `building_records.json` | `member_count`, `member_count_all`, `has_vtu_member`, `latest_membership_year`, `member_share_pct` |
| `filter_config.json` | `membership_years`, `membership_year_metric` |
| `blocks.geojson` | `member_buildings`, `total_members`, `member_share` |

## 13. What this buys

- One-directional contract: `sica_core` derives, the frontend renders.
- `index.html` from 22.16 MB to a shell; total transfer from ~4.2 MB gzipped to
  about 2.1 MB. Measured on the real export: with coordinates rounded to 6
  decimals, the artifact set is 2.05 MB gzipped, `blocks.geojson` 1.45 MB of
  it. Unrounded (15-decimal coordinates) it was 4.38 MB, no smaller than the
  Folium page.
- `sica_mapping` deleted (3,555 Python lines, 521 of them relocated into
  `sica_core`); `folium` dropped. Python emits no markup.
- A real backend/frontend split: `sica_core` is a data product whose public
  interface is the artifact directory, and `frontend/` is an ordinary Vite
  project that can grow on its own. A second frontend is a second consumer of
  the same directory, not a fork of the renderer.
- Frontend iteration on hot reload instead of a ~19s ingest-and-render cycle.
- The CLAUDE.md §5 TypeScript work reduced to converting `wiring.js` module by
  module inside a project that already builds, with the data side finished.
- One place for the CLAUDE.md §3 sensitivity filter to live — and, once it
  exists, the thing that unblocks automated deploys (§11).
