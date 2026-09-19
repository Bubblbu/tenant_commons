# Data Sources

*Reference catalog. Update whenever a source is added, re-fetched, or its details change — see [Adding a new source](#adding-a-new-source) at the bottom.*

Last updated: 2026-09-18

---

## Scope

This document catalogs **acquisition** — how each external dataset gets from its
origin into a file under `data/`, and what's known about that origin (license,
format, cadence, quirks). It stops there.

- What happens *after* acquisition — parsing a `data/raw/**` file into `sica_core`'s
  SQLite tables — is covered by the code itself: one `ingest/raw_<source>.py`
  module per source under `src/sica_core/ingest/`, each with an explicit
  column allow-list. That pattern is the target for new sources going
  forward; this doc doesn't re-describe it.
- **Manually-curated data** (tenant reports, common-ownership research) is not
  an acquisition source and isn't cataloged here — see
  [Manual curation](#manual-curation) below for where it actually lives.
- This doc is the detailed per-source reference. `CLAUDE.md` Section 3 stays
  the short decisions/roadmap summary and links here.

## Conventions

- **Retain originals.** Where a source arrives as a document (FOI PDF, a
  scraped page), the as-received file is kept in its `data/raw/<source>/`
  folder beside the extracted CSV. Nothing under `data/` is tracked by git;
  the record of what was fetched, when and how is that folder's `MANIFEST.md`.
- **Script vs. manual.** A source gets a `scripts/fetch_<source>.py` (see
  `fetch_coops.py` for the pattern: documented, replayable offline via a
  `--html-file`-style flag) if it's expected to be re-pulled periodically.
  A stable, official one-off pull (a City Open Data export, an FOI response)
  is fine as a documented manual procedure — write out the exact steps in
  that source's entry instead.
- **No in-place hand edits.** Once a CSV is retained as "this is what the
  source gave us," don't hand-edit it directly (e.g. in LibreOffice) — that
  silently blurs source data with manual correction and breaks the retained
  original as a source of truth. Fix problems upstream (re-derive from the
  retained original) or record the correction as a dated note in that
  source's entry.
- **TODO markers** below are real gaps, not rhetorical — facts only you have
  (FOI reference numbers, exact portal URLs) that weren't recoverable from
  the repo. Fill them in as you get a chance; they're not blocking anything.

---

## Summary

| Source | Category | Last fetched | Refresh cadence | Consumed by |
|---|---|---|---|---|
| [`buildings.csv`](#buildingscsv) | Derived: built by `prepare_data.py` from Open Data + FOI | 2026-09-18 | Rebuilt after a fetch | `sica_mapping`, `sica_core` |
| [`property_addresses.csv`](#property_addressescsv) | Open Data portal | 2026-09-18 | On demand (`fetch_cov_open_data.py`) | `sica_mapping`, `sica_core` |
| [`block-outlines.csv`](#block-outlinescsv) | Open Data portal | 2026-09-18 | On demand (`fetch_cov_open_data.py`) | `sica_mapping`, `sica_core` |
| [`block-numbers.csv`](#block-numberscsv) | Open Data portal | 2026-09-18 | On demand (`fetch_cov_open_data.py`) | `sica_mapping`, `sica_core` |
| [`local-area-boundary.csv`](#local-area-boundarycsv) | Open Data portal | 2026-09-18 | On demand (`fetch_cov_open_data.py`) | `sica_mapping` |
| [`sra_housing_combined.csv`](#sra_housing_combinedcsv) | FOI? — unverified ⚠️ | 2026-07-30 (file date) | TODO | `sica_mapping`, `sica_core` |
| [`rezoning_applications.csv`](#rezoning_applicationscsv) | FOI? — unverified ⚠️ | 2026-07-30 (file date) | TODO | `sica_mapping`, `sica_core` |
| [`coops_vancouver.csv`](#coops_vancouvercsv) | Third-party online | 2026-08-04 | Periodic (re-run script) | `sica_mapping`, `sica_core` |
| [`samwise-export.csv`](#samwise-exportcsv) | Third-party online (BC LOTR, via `samwise`) | 2026-09-16 | Ad hoc | `sica_core` |
| [`membership_full.csv`](#membership_fullcsv) | Internal / organizational | TODO | VTU's own cadence | `sica_mapping`, `sica_core` |
| [`vtu_members.csv`](#vtu_memberscsv) | Internal / organizational — likely orphaned ⚠️ | — | — | none found |

⚠️ = flagged for your attention, see that source's entry.

---

## Open Data portal

Sources pulled from the City of Vancouver's Open Data platform
(opendata.vancouver.ca). All fetched by
`scripts/fetch_cov_open_data.py`. Column names like `geo_point_2d`, `geom`,
`geo_local_area` are the portal's own naming convention, visible directly in
the raw CSVs.

### `buildings.csv`

- **What it is:** the core building/landlord table — address, unit count,
  year built, assessed land/building value, zoning, plus City rental
  business-licence fields (`bsns_group`, `bsns_name`, `bsns_trade_name`,
  `bsns_type`).
- **Origin and access method:** Fetched directly from Open Data by `scripts/fetch_cov_open_data.py` (buildings.csv is built from several of those files plus the FOI extracts by `scripts/prepare_data.py`). Until 2026-09 this came from a separate pipeline repo, `vhd`, since retired; its logic now lives in `src/sica_core/prepare/`.
- **`management`, `n_issues`, `issues_details` are part of this source**,
  not a hand-added local artifact — confirmed by their presence in `vhd`'s
  own `processed/buildings.csv` output (sourced from `landlord_mapping.toml`
  there). `notes`/`prospect` are *not* in `vhd`'s output at all — genuinely
  local/hand-added columns of unclear origin; kept verbatim by
  `raw_buildings.py` but worth eventually tracing or retiring.
  `vtu_members`/`westend_inbox`/`vtu_main_inbox`/`vtu_building` remain
  correctly identified as a one-off local artifact (see
  [[project_organizer_view_deferred]]) — `raw_buildings.py` strips them.
- **License/attribution:** TODO — Vancouver Open Data's default license
  (Open Government Licence – Vancouver) likely applies to the underlying
  Open Data portions; the datasets are the ones listed in
  `src/sica_core/fetch/cov_open_data.py`; confirm the license per dataset.
- **Geographic scope:** citywide (no West-End restriction — see CLAUDE.md
  Section 2, Q3).
- **Format/known quirks:**
  - `value_land`/`value_bldg`: **as of the 2026-08-07 `vhd` refresh, plain
    numeric city-wide.** Historically (pre-refresh) 100% of West End rows
    arrived as `"$35,407,000.00"`-style strings while the rest of the city
    was plain numeric — an artifact of West End having gone through a
    separate hand path in the old pipeline. `vhd`'s rebuild replaced that
    two-tier assembly with one uniform Open Data pull, so the formatting
    split is gone. `raw_buildings.py::_stringify_money()` normalizes either
    shape to a clean string for TEXT storage; `ingest/merge.py::_parse_money()`
    still does the actual numeric parse at merge time and still handles
    both shapes, in case a future pull reintroduces currency formatting for
    some subset.
  - `pid`/`folio`: semicolon-joined lists when a building spans multiple
    parcels (1,045/5,146 rows in the 2026-08-07 pull). ~7% of
    `property_addresses.csv` rows carry a plan number (e.g. `EPS5265`)
    instead of a numeric PID (bare-land-strata/common-property parcels) —
    `folio`/`value_land`/`value_bldg` are null on those.
  - `secondary_addresses` (new 2026-08-07): semicolon-joined list of other
    civic addresses VanMaps resolves to the same building as `address`
    (e.g. multiple street-facing entrances on one podium building). Used by
    `src/sica_mapping/data/overlays.py::_load_secondary_address_index()` as
    a fallback when matching co-op/SRO records that were geocoded to a
    secondary address rather than the building's primary one — lifted
    SRO/SRA match rate from 41/171 (24%) to 53/171 (31%) on the 2026-08-07
    data. Not used for rezoning matching (keys off project name, not a
    civic address).
  - `folio`, `zoning_district`, `zoning_classification`, `bsns_subtype`:
    also new in the 2026-08-07 pull; stored verbatim, not yet consumed
    downstream beyond raw browsability.
  - `n_pids`, `is_primary_address` (`address is primary?`), `bldg_land_ratio`,
    `value_per_unit`: present in older pulls, **absent** from `vhd`'s
    2026-08-07 output. Nothing downstream reads them (bldg_land_ratio is
    recomputed from value_bldg/value_land at merge time if missing) — left
    in `raw_buildings.py`'s column list as always-null rather than removed.
  - `clean_address` (ported unchanged) rewrites any word starting with ` str` (e.g. `strathcona` becomes `stathcona`). Both sides of each join use the same function, so matching works; do not change it without rebuilding everything.
- **Output location:** `data/derived/buildings.csv`.
- **Consumed by:** `sica_mapping` (`config.toml` → `buildings`), `sica_core`
  (`ingest/raw_buildings.py`).
- **Refresh cadence:** rebuilt by `prepare_data.py` after each fetch. Last
  fetched 2026-09-18.

### `property_addresses.csv`

- **What it is:** civic addresses with lat/lon and local-area tagging —
  used to geocode buildings and recover missing coordinates.
- **Origin and access method:** Fetched directly from Open Data by `scripts/fetch_cov_open_data.py` (buildings.csv is built from several of those files plus the FOI extracts by `scripts/prepare_data.py`). Until 2026-09 this came from a separate pipeline repo, `vhd`, since retired; its logic now lives in `src/sica_core/prepare/`.
- **License/attribution:** Open Government Licence – Vancouver (Open Data
  portal default) — TODO: confirm no additional attribution needed.
- **Geographic scope:** citywide (filtered to West End downstream by the
  pipelines, not in the file itself).
- **Format/known quirks:** `geo_point_2d` holds `"lat,lon"` as a single
  string, parsed downstream. `sica_core/ingest/raw_addresses.py` raises on
  any column not in its allow-list rather than silently dropping it.
  Header casing has varied between pulls (`Geo Local Area` vs
  `geo_local_area`) — harmless, `normalize_cols()` lowercases before the
  allow-list check either way.
  The Open Data export gained a `note` column in 2026-09 (populated on
  ~1,247 of ~99.7k rows with the text "Translated name until colonial
  systems support multi-lingual characters."); it is stored in
  `raw_addresses.note`.
- **Output location:** `data/raw/cov_open_data/property-addresses.csv`.
- **Consumed by:** `sica_mapping` (`config.toml` → `addresses`), `sica_core`
  (`ingest/raw_addresses.py`).
- **Refresh cadence:** on demand. Last fetched 2026-09-18.

### Fetching Open Data

`scripts/fetch_cov_open_data.py` downloads the 8 Open Data datasets into
`data/raw/cov_open_data/` (CSV for the ingest, GeoJSON for the prepare steps).
Then `scripts/prepare_data.py` rebuilds `data/derived/`. See `data/README.md`
for the full rebuild order.

### `block-outlines.csv`

- **What it is:** polygon geometry for city blocks, used for block-level
  choropleth aggregation (unit totals, VTU saturation, median year built).
- **Origin:** TODO — exact dataset URL/name.
- **License/attribution:** TODO.
- **Geographic scope:** citywide; `sica_core/ingest/blocks.py` keeps every
  row and records a `in_west_end_bbox` flag rather than dropping rows
  outside the pilot bbox, so the table stays fully browsable.
- **Access method:** scripted, `scripts/fetch_cov_open_data.py` (dataset `block-outlines`).
- **Format/known quirks:** polygon geometry lives in a `geom` column,
  parsed via `sica_core/geometry.py::parse_geom`.
- **Output location:** `data/raw/cov_open_data/block-outlines.csv`.
- **Consumed by:** `sica_mapping` (`config.toml` → `blocks`), `sica_core`
  (`ingest/blocks.py`).
- **Refresh cadence:** on demand (`fetch_cov_open_data.py`); last fetched 2026-09-18.

### `block-numbers.csv`

- **What it is:** point locations with a `label` and `geo_local_area`, used
  to resolve which of the 22 official local areas a block/building falls
  in (point-in-polygon primary, nearest-centroid fallback).
- **Origin:** confirmed to be Vancouver Open Data's "block-numbers" dataset
  by name (`src/sica_mapping/data/spatial.py` docstring cites it directly);
  exact URL still TODO.
- **License/attribution:** TODO.
- **Geographic scope:** citywide.
- **Access method:** scripted, `scripts/fetch_cov_open_data.py` (dataset `block-numbers`).
- **Format/known quirks:** none noted beyond standard portal column naming
  (`geom`, `geo_point_2d`). `sica_core/ingest/block_numbers.py` raises on
  unexpected columns.
- **Output location:** `data/raw/cov_open_data/block-numbers.csv`.
- **Consumed by:** `sica_mapping` (`spatial.py::resolve_local_area_from_block_numbers`),
  `sica_core` (`ingest/block_numbers.py`).
- **Refresh cadence:** rare — local area/block boundaries change
  infrequently. Re-pull only if the City revises them.

### `local-area-boundary.csv`

- **What it is:** the 22 official Vancouver local-area boundary polygons,
  used to assign a `local_area` to overlay records (co-ops, SRO/SRA,
  rezoning applications) that don't already carry one that matches the
  sidebar's neighbourhood checkboxes.
- **Origin and access method:** Fetched directly from Open Data by `scripts/fetch_cov_open_data.py` (buildings.csv is built from several of those files plus the FOI extracts by `scripts/prepare_data.py`). Until 2026-09 this came from a separate pipeline repo, `vhd`, since retired; its logic now lives in `src/sica_core/prepare/`.
- **License/attribution:** Open Government Licence – Vancouver (Open Data
  portal default) — TODO: confirm no additional attribution needed.
- **Geographic scope:** citywide, all 22 local areas.
- **Format/known quirks:** GeoJSON-style `FeatureCollection`, `properties.name`
  used as the area label. `src/sica_mapping/data/overlays.py` deliberately
  does *not* trust each overlay source's own free-text area field (e.g. the
  SRO CSV's "Area" is a DTES-style composite label) — always resolves via
  point-in-polygon against this file instead.
- **Output location:** `data/raw/cov_open_data/local-area-boundary.csv`.
- **Consumed by:** `sica_mapping` only (`overlays.py`) — not yet ingested
  into `sica_core`.
- **Refresh cadence:** rare — official boundaries change infrequently. Last
  fetched 2026-09-18.

---

## FOI records

**⚠️ Category unverified.** Both files below were assumed to be FOI
responses (per `CLAUDE.md`'s "City of Vancouver FOI records" source type),
but nothing in the repo actually confirms that:

- `rezoning_applications.csv`'s `Link` column points to Wayback
  Machine/archive-it.org captures of individual `rezoning.vancouver.ca`
  application pages — consistent with **manually compiling this by browsing
  archived web pages**, not a formal FOI request.
- `sra_housing_combined.csv`'s own `match_method` column (values like
  `"address"`) suggests it's already a **merge of at least two source
  lists** by address — possibly assembled by a third party (an advocacy
  group's SRO hotel registry is a plausible candidate) rather than a direct
  FOI response.

TODO: confirm the actual origin of each and re-file it under the correct
category (most likely "Third-party online" for one or both) once confirmed.
Sections kept here for now since that's the best guess available.

### `sra_housing_combined.csv`

- **What it is:** SRO/SRA (single-room-occupancy) hotel inventory — owner,
  operator, operator group, ownership group, registered room count,
  occupancy status.
- **Origin:** TODO (see category warning above) — request date, reference
  number if FOI; source URL/organization if not.
- **License/attribution:** TODO.
- **Geographic scope:** DTES/Chinatown/Gastown/Strathcona-concentrated (per
  the file's own `Area` field), not West End.
- **Access method:** TODO — no script; unclear if this can even be
  re-fetched the same way twice (a merged/combined file may not have a
  single re-runnable source).
- **Format/known quirks:** the file's own `match_method` column is an
  upstream address-matching flag from whoever combined the source lists —
  unrelated to and not used by this project's own address-key matching in
  `src/sica_mapping/data/overlays.py`.
- **Provenance/original retained:** **not yet** — no original document is
  currently kept. Per the retain-originals convention above, the source
  document(s) this was combined from should be saved under
  `data/raw/cov_foi/` going forward, with a note on how the merge
  was done. TODO once the origin is confirmed.
- **Output location:** `data/raw/cov_foi/sra_housing_combined.csv`.
- **Consumed by:** `sica_mapping` (`overlays.py`) — 53/171 rows (31%, since
  the 2026-08-07 `secondary_addresses` fallback) match an existing building
  by address; the rest surface as standalone unmatched markers. Also
  `sica_core` (`ingest/raw_sro.py`, since 2026-08-07) — raw storage only,
  for browsability; the address-key matching above is not repeated in
  sica_core.
- **Refresh cadence:** TODO.

### `rezoning_applications.csv`

- **What it is:** rezoning application records — status (open/approved),
  category, status detail, and a link to the application's page.
- **Origin:** TODO (see category warning above) — likely compiled from
  `rezoning.vancouver.ca` (live and/or Wayback-archived), possibly
  alongside or instead of a formal FOI response.
- **License/attribution:** TODO.
- **Geographic scope:** citywide.
- **Access method:** TODO — if compiled from archived web pages by hand,
  document the actual steps (which archive snapshots, what was pulled from
  each) rather than leaving it as "FOI."
- **Format/known quirks:** `id` (e.g. `RZ285`) is **not** reliably unique
  per row — a multi-site "umbrella" application can cover two entirely
  different addresses/lat-lons as separate rows with the same `id`
  (confirmed via a real duplicate-key collision during testing — see
  `overlays.py`). `name` is free text, not a clean address (e.g.
  `"2165-2195 and 2205-2291 W 45th Av (Dunbar Ryerson United Church)"`) —
  parsed by stripping from the first `(`, then splitting on
  `" and "`/`"&"`/`";"` and keying the first fragment. Most rezoning
  applications (churches, single-family lots, commercial, multi-lot
  assemblies) don't correspond to any row in `buildings.csv` at all,
  regardless of parsing quality — ~43/377 (11%) match.
- **Provenance/original retained:** **not yet** — TODO, same as above.
- **Output location:** `data/raw/cov_foi/rezoning_applications.csv`.
- **Consumed by:** `sica_mapping` (`overlays.py`), split into open/closed
  status groups. Also `sica_core` (`ingest/raw_rezoning.py`, since
  2026-08-07) — raw storage only, for browsability.
- **Refresh cadence:** TODO.

---

## Third-party online

Data pulled from an external organization's own website or public dataset —
not the City's Open Data portal, not FOI, not VTU's own systems.

### `coops_vancouver.csv`

- **What it is:** CHF BC's ("Co-operative Housing Federation of BC")
  province-wide co-op housing directory, filtered to Vancouver — address,
  coordinates, waitlist status, ownership model, bedroom range, home type,
  accessibility/seniors/pets/RGI features, source links.
- **Origin:** [chf.bc.ca/find-a-co-op](https://www.chf.bc.ca/find-a-co-op/) —
  the page embeds its entire dataset as inline JSON in a
  `<script class="coop-explorer__data">` tag; no separate API call needed.
- **License/attribution:** TODO — confirm CHF BC's terms of use for reuse
  of this data, and what attribution (if any) is expected before this
  reaches the public map.
- **Geographic scope:** filtered to CHF's own `location.city == "Vancouver"`
  field (city-wide, not clipped to West End or any block/bbox geometry —
  deliberately, since this isn't scoped to the pilot).
- **Access method:** **scripted** — `scripts/fetch_coops.py`. Supports
  `--html-file` for an offline replay against a previously-saved page, and
  `--city`/`--out` overrides. This is the reference example for how a
  scripted source should be documented.
- **Format/known quirks:** the page blocks bare-looking scripted requests —
  the script sends a normal browser `User-Agent` to get a plain 200. Filter
  matches on `"Vancouver"` exactly; if CHF ever changes the field to e.g.
  `"City of Vancouver"`, the script's `normalize_coops()` raises rather than
  silently returning zero rows.
- **Provenance/original retained:** not currently — the fetched HTML is not
  saved, only the derived CSV. Per the retain-originals convention, future
  re-runs could optionally save the fetched HTML under
  `data/raw/chf_bc/<date>.html` for exact replay/audit later;
  not done yet (TODO, low priority given the script re-fetches live data
  cleanly).
- **Output location:** `data/raw/chf_bc/coops_vancouver.csv`.
- **Consumed by:** `sica_mapping` (`overlays.py`) — 42/117 rows (36%) match
  an existing building by address; the rest surface as standalone unmatched
  markers. Also `sica_core` (`ingest/raw_coops.py`, since 2026-08-07) — raw
  storage only, for browsability.
- **Refresh cadence:** periodic, re-run by hand
  (`python scripts/fetch_coops.py`) when a refresh is wanted. 117 co-ops as
  of 2026-08-04 (287 province-wide).

### `samwise-export.csv`

- **What it is:** BC Land Owner Transparency Registry (LOTR) ownership
  disclosures for researched properties — one row per (property, reporting
  corporation, disclosed interest holder). Collected via `samwise`, a
  separate research tool (`../samwise/` alongside this repo) that queries
  LTSA's public LOTR search per PID. 3,538 rows / 1,111 distinct PIDs as of
  the 2026-09-16 export.
- **Origin:** BC's Land Owner Transparency Registry
  ([ltsa.ca/lotr](https://ltsa.ca/property-owner-transparency/land-owner-transparency-registry/)),
  a government-mandated public disclosure of beneficial property ownership.
  Retrieved per-PID via `samwise`, not a bulk/API download.
- **License/attribution:** TODO — confirm LTSA's terms for reuse/
  redistribution of search results; this is public disclosure data, but
  redistribution terms haven't been checked.
- **⚠️ Sensitivity:** although LOTR disclosure is legally public, the raw
  export contains real individuals' names, citizenship, and city/province of
  residence. Per CLAUDE.md's sensitivity model and the standing rule against
  committing raw personal-data exports (same reasoning as
  `data/raw/nationbuilder/`), `data/raw/samwise/*` is gitignored — kept local-only,
  never committed. `raw_lotr_ownership` in `data/derived/sica_core.db` (also
  gitignored) is the only persisted copy.
- **Geographic scope:** whatever PIDs `samwise` has been pointed at so
  far — not systematically all of West End yet, opportunistic per
  `CLAUDE.md` Section 7's "secondary, opportunistic scope."
- **Access method:** manual — export generated by the separate `samwise`
  tool, dropped into `data/raw/samwise/samwise-export.csv` by hand. Not
  scripted from this repo's side.
- **Format/known quirks:** 44 columns. Many rows are self-referential (a
  corporation disclosing itself as its own direct interest holder — no new
  information) or redacted under LOTR s. 30(4) (holder identity withheld).
  Individual names arrive pre-combined as `"LAST, GIVEN"` in `holder_name`.
  See `ingest/lotr_claims.py`'s docstring for how these are filtered before
  becoming claims.
- **Provenance/original retained:** locally only — see Sensitivity above.
  `raw_lotr_ownership` stores the export verbatim in SQLite for
  browsability (see `ingest/raw_lotr.py`), but that database is itself
  gitignored, same as the source CSV.
- **Output location:** `data/raw/samwise/samwise-export.csv` (gitignored,
  local-only — see Sensitivity above).
- **Consumed by:** `sica_core` only — `ingest/raw_lotr.py` (raw storage)
  and `ingest/lotr_claims.py` (derives `common_owner` `ownership_claims`
  from shared beneficial-interest holders). Not part of `sica_mapping`'s
  public build; not wired into the main `run_ingest()` pipeline — imported
  standalone via `scripts/import_lotr_claims.py`.
- **Refresh cadence:** ad hoc, whenever `samwise` produces a new export —
  re-run `scripts/import_lotr_claims.py` to pick it up.

---

## Internal / organizational

VTU's own data, not pulled from any public source. The one category here
that's genuinely sensitive — see `CLAUDE.md` Section 3's sensitivity model
rather than this doc for how field-level access is handled.

### `membership_full.csv`

- **What it is:** VTU's NationBuilder membership export — 154 columns
  (emails, phone, ethnicity, religion, donation history, marital status,
  and more), of which only `nationbuilder_id`, `primary_address1`,
  `tag_list`, and `updated_at` are ever read.
- **Origin:** VTU's NationBuilder account, exported by VTU on its own
  cadence. Not a public pull — controlled internally.
- **License/attribution:** N/A (internal data) — but see sensitivity note
  below regarding what may ever be exported publicly.
- **⚠️ Sensitivity:** this is the one source containing directly
  identifying/sensitive tenant data. `sica_core/ingest/membership.py`
  enforces an explicit column allow-list at the CSV-read layer itself
  (`pd.read_csv(usecols=...)`), so the other ~150 columns never become an
  in-memory column, let alone a database row. The address column is
  hardcoded to `primary_address1` rather than found via substring search —
  a reordered NationBuilder export could otherwise silently start reading a
  different address-like column (`address_address1`, `billing_address1`,
  `mailing_address1`, `work_address1`, `user_submitted_address1` all exist)
  with no error. See `CLAUDE.md` Section 3 ("Sensitivity model") for the
  broader field-level flagging approach this feeds into.
- **Access method:** manual export from NationBuilder by VTU; not
  scriptable from this project's side.
- **Output location:** `data/raw/nationbuilder/membership_full.csv`.
- **Consumed by:** `sica_mapping` (`data/vtu.py`), `sica_core`
  (`ingest/membership.py`).
- **Refresh cadence:** VTU's own cadence — TODO: confirm how often VTU
  re-exports and whether there's a standing arrangement for this.

### `vtu_members.csv`

- **⚠️ Likely orphaned.** 566 rows, only 3 columns
  (`nationbuilder_id`, `primary_address1`, `address`) — looks like an older,
  already-narrowed export that predates `membership_full.csv`. No code in
  either `sica_mapping` or `sica_core` references this file by name
  (confirmed via repo-wide search); `config.toml`'s `vtu` path points at
  `membership_full.csv` only.
- **Recommendation:** confirm it's genuinely unused, then either delete it
  or move it out of `data/raw/nationbuilder/`, since it looks like a live input there.

---

## Manual curation

Not cataloged here — manually-curated ownership intelligence (tenant
reports, common-ownership research) is modeled as its own first-class,
auditable table (`ownership_claims`), not a file with a URL or a fetch
cadence. See `CLAUDE.md` Section 3 ("Claims model") for the full schema and
rationale.

---

## Adding a new source

1. Pick a category: Open Data portal / FOI records / Third-party online /
   Internal-organizational. If it doesn't fit any of these, it's probably
   manual curation instead — see above, don't add it here.
2. Decide script vs. manual (see [Conventions](#conventions)). If scripted,
   base it on `scripts/fetch_coops.py`'s shape: documented source URL,
   offline-replayable, fails loudly on unexpected shape rather than
   silently returning something wrong or empty.
3. If it arrives as a document (PDF, spreadsheet, saved HTML) rather than a
   clean CSV, save the original under `data/raw/<source_name>/` and
   note how it was turned into the CSV the pipeline actually reads.
4. Add a row to the [Summary](#summary) table.
5. Add a detail section with these fields: **What it is**, **Origin**,
   **License/attribution**, **Geographic scope**, **Access method**,
   **Format/known quirks**, **Provenance/original retained** (if
   applicable), **Output location**, **Consumed by**, **Refresh cadence**.
6. If it lands in `data/` as a plain CSV meant for `sica_core`, add a
   corresponding `ingest/raw_<source>.py` module following the existing
   pattern (explicit column allow-list, raise on unexpected columns) — see
   [Scope](#scope) above for why that's not re-described in this doc.
