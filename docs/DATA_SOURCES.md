# Data Sources

*Reference catalog. Update whenever a source is added, re-fetched, or its details change — see [Adding a new source](#adding-a-new-source) at the bottom.*

Last updated: 2026-09-18

---

## Scope

This document catalogs **acquisition** — how each external dataset gets from its
origin into a file under `data/`, and what's known about that origin (license,
format, cadence, quirks). It stops there.

- What happens *after* acquisition — parsing a `data/raw/**` file into `tc_core`'s
  SQLite tables — is covered by the code itself: one `ingest/raw_<source>.py`
  module per source under `src/tc_core/ingest/`, each with an explicit
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
| [`buildings.csv`](#buildingscsv) | Derived: built by `prepare_data.py` from Open Data + FOI | 2026-09-18 | Rebuilt after a fetch | `tc_core` |
| [`property_addresses.csv`](#property_addressescsv) | Open Data portal | 2026-09-18 | On demand (`fetch_cov_open_data.py`) | `tc_core` |
| [`block-outlines.csv`](#block-outlinescsv) | Open Data portal | 2026-09-18 | On demand (`fetch_cov_open_data.py`) | `tc_core` |
| [`block-numbers.csv`](#block-numberscsv) | Open Data portal | 2026-09-18 | On demand (`fetch_cov_open_data.py`) | `tc_core` |
| [`local-area-boundary.csv`](#local-area-boundarycsv) | Open Data portal | 2026-09-18 | On demand (`fetch_cov_open_data.py`) | none (`tc_core` uses the GeoJSON export) |
| [`city-owned-properties.csv`](#city-owned-propertiescsv) | Open Data portal | 2026-09-24 | On demand (`fetch_cov_open_data.py`) | `tc_core` |
| [`business-licences-2013-to-2024.csv`](#business-licences-2013-to-2024csv) | Open Data portal (2024 slice) | 2026-10-20 | Static (historic dataset) | `tc_core` |
| [`sra_housing_combined.csv`](#sra_housing_combinedcsv) | FOI? — unverified ⚠️ | 2026-07-30 (file date) | TODO | `tc_core` |
| [`rezoning_applications.csv`](#rezoning_applicationscsv) | FOI? — unverified ⚠️ | 2026-07-30 (file date) | TODO | `tc_core` |
| [`coops_vancouver.csv`](#coops_vancouvercsv) | Third-party online | 2026-08-04 | Periodic (re-run script) | `tc_core` |
| [Landlord listings](#landlord-listings) | Third-party online (company websites) | 2026-09-30 | Periodic (re-run scripts) | `tc_core` |
| [`samwise-export.csv`](#samwise-exportcsv) | Third-party online (BC LOTR, via `samwise`) | 2026-09-16 | Ad hoc | `tc_core` |
| [VTU membership](#vtu-membership-nationbuilder--retired-2026-10-20) | Internal / organizational — retired | — | — | none |

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
- **Origin and access method:** Fetched directly from Open Data by `scripts/fetch_cov_open_data.py` (buildings.csv is built from several of those files plus the FOI extracts by `scripts/prepare_data.py`). Until 2026-09 this came from a separate pipeline repo, `vhd`, since retired; its logic now lives in `src/tc_core/prepare/`.
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
  `src/tc_core/fetch/cov_open_data.py`; confirm the license per dataset.
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
    `src/tc_core/ingest/overlay_sources.py::load_secondary_address_index()` as
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
  - Address keying used to go through `prepare/address.py`'s `clean_address`, which rewrote any word starting with ` str` (e.g. `strathcona` became `stathcona`) via an unguarded substring replace. That module is retired (2026-09) in favor of `tc_core.normalize.addr_key_from_freeform`, used uniformly by `prepare/`, `ingest/`, and membership matching alike — its word-boundary-safe replacement doesn't corrupt `strathcona`, and it keeps punctuation `clean_address` used to strip (apostrophes, hyphens: `lamey's mill rd`, not `lameys mill rd`), while still stripping a trailing `*` footnote marker the FOI rental list uses on some addresses.
  - `bsns_year`: the business-licence `folderyear` this build used, as a four-digit year (the City publishes two digits). Dataset-level — the same on every row. The export publishes it as `filter_config.licence_year` for the popup's licence provenance.
  - **Licence-only buildings (2026-09-27).** Rows used to come only from the FOI
    rental inventory and the non-market housing list, with licences attached
    afterwards, so a licensed rental building missing from the inventory never
    reached the map (mostly buildings finished since the inventory was compiled).
    `prepare/buildings.py::licence_only_rentals()` now adds current Long-term
    Rental licences as buildings when their fees pay for at least 5 dwelling units
    (summed per address) or they are non-profit housing, and no inventory building
    is on the same address, the same parcel, or within 20 civic numbers on the same
    street with the same unit count. `LICENCE_ONLY_EXCLUDED` keeps out non-tenancy
    cases (serviced suites, a retirement residence, hostels). 253 buildings in the
    2026 data: 204 with ~10,800 licensed units, the rest non-profit (no count in the fee).
  - `building_source`: which City list the building came from — `rental inventory`
    (FOI), `non-market housing list`, or `rental licence` (the licence-only rows
    above). Carried to `buildings.building_source` and the building records; when
    several source rows merge into one building, a City list wins over a licence.
    For `rental licence` rows, `units` is read from the fee by
    `prepare/licence_fees.py::decode_fee` (rates from the Licence By-law, see
    `data/raw/cov_bylaws/MANIFEST.md`) and the popup says "licensed units" —
    except on SROs, where the ingest's SRO fill-in may have set `units` to the
    registry's room count.
  - `source_licences` (rental licence rows only): the `;`-joined City licence
    numbers (`licencenumber`) behind the row, for `bsns_year`'s folderyear.
    Licence numbers change every year, so they identify rows in the
    `business-licences.geojson` fetched on the date in
    `raw/cov_open_data/MANIFEST.md`. Kept in `raw_buildings`; a building reaches it
    through `buildings.source_row_ids`.
- **Output location:** `data/derived/buildings.csv`.
- **Consumed by:** `tc_core` (`ingest/raw_buildings.py`).
- **Refresh cadence:** rebuilt by `prepare_data.py` after each fetch. Last
  fetched 2026-09-18.

### `property_addresses.csv`

- **What it is:** civic addresses with lat/lon and local-area tagging —
  used to geocode buildings and recover missing coordinates.
- **Origin and access method:** Fetched directly from Open Data by `scripts/fetch_cov_open_data.py` (buildings.csv is built from several of those files plus the FOI extracts by `scripts/prepare_data.py`). Until 2026-09 this came from a separate pipeline repo, `vhd`, since retired; its logic now lives in `src/tc_core/prepare/`.
- **License/attribution:** Open Government Licence – Vancouver (Open Data
  portal default) — TODO: confirm no additional attribution needed.
- **Geographic scope:** citywide (filtered to West End downstream by the
  pipelines, not in the file itself).
- **Format/known quirks:** `geo_point_2d` holds `"lat,lon"` as a single
  string, parsed downstream. `tc_core/ingest/raw_addresses.py` raises on
  any column not in its allow-list rather than silently dropping it.
  Header casing has varied between pulls (`Geo Local Area` vs
  `geo_local_area`) — harmless, `normalize_cols()` lowercases before the
  allow-list check either way.
  The Open Data export gained a `note` column in 2026-09 (populated on
  ~1,247 of ~99.7k rows with the text "Translated name until colonial
  systems support multi-lingual characters."); it is stored in
  `raw_addresses.note`.
- **Output location:** `data/raw/cov_open_data/property-addresses.csv`.
- **Consumed by:** `tc_core`
  (`ingest/raw_addresses.py`).
- **Refresh cadence:** on demand. Last fetched 2026-09-18.

### Fetching Open Data

`scripts/fetch_cov_open_data.py` downloads the 8 Open Data datasets into
`data/raw/cov_open_data/` (CSV for the ingest, GeoJSON for the prepare steps).
Then `scripts/prepare_data.py` rebuilds `data/derived/`. See `data/README.md`
for the full rebuild order.

### `block-outlines.csv`

- **What it is:** polygon geometry for city blocks, stored as the raw
  `raw_blocks` table. The export joins buildings to it by point-in-polygon
  for the public map's block choropleth (unit totals, median year built);
  blocks are not an entity and nothing else references them.
- **Origin:** TODO — exact dataset URL/name.
- **License/attribution:** TODO.
- **Geographic scope:** citywide; `tc_core/ingest/blocks.py` keeps every
  row with parseable geometry.
- **Access method:** scripted, `scripts/fetch_cov_open_data.py` (dataset `block-outlines`).
- **Format/known quirks:** polygon geometry lives in a `geom` column,
  parsed via `tc_core/geometry.py::parse_geom`.
- **Output location:** `data/raw/cov_open_data/block-outlines.csv`.
- **Consumed by:** `tc_core`
  (`ingest/blocks.py`).
- **Refresh cadence:** on demand (`fetch_cov_open_data.py`); last fetched 2026-09-18.

### `block-numbers.csv`

- **What it is:** point locations with a `label` and `geo_local_area`, used
  to resolve which of the 22 official local areas a block/building falls
  in (point-in-polygon primary, nearest-centroid fallback).
- **Origin:** confirmed to be Vancouver Open Data's "block-numbers" dataset
  by name (the retired `sica_mapping` `spatial.py` docstring cited it directly);
  exact URL still TODO.
- **License/attribution:** TODO.
- **Geographic scope:** citywide.
- **Access method:** scripted, `scripts/fetch_cov_open_data.py` (dataset `block-numbers`).
- **Format/known quirks:** none noted beyond standard portal column naming
  (`geom`, `geo_point_2d`). `tc_core/ingest/block_numbers.py` raises on
  unexpected columns.
- **Output location:** `data/raw/cov_open_data/block-numbers.csv`.
- **Consumed by:** `tc_core` (`ingest/block_numbers.py`).
- **Refresh cadence:** rare — local area/block boundaries change
  infrequently. Re-pull only if the City revises them.

### `local-area-boundary.csv`

- **What it is:** the 22 official Vancouver local-area boundary polygons,
  used to assign a `local_area` to overlay records (co-ops, SRO/SRA,
  rezoning applications) that don't already carry one that matches the
  sidebar's neighbourhood checkboxes.
- **Origin and access method:** Fetched directly from Open Data by `scripts/fetch_cov_open_data.py` (buildings.csv is built from several of those files plus the FOI extracts by `scripts/prepare_data.py`). Until 2026-09 this came from a separate pipeline repo, `vhd`, since retired; its logic now lives in `src/tc_core/prepare/`.
- **License/attribution:** Open Government Licence – Vancouver (Open Data
  portal default) — TODO: confirm no additional attribution needed.
- **Geographic scope:** citywide, all 22 local areas.
- **Format/known quirks:** GeoJSON-style `FeatureCollection`, `properties.name`
  used as the area label. `src/tc_core/ingest/overlays.py` deliberately
  does *not* trust each overlay source's own free-text area field (e.g. the
  SRO CSV's "Area" is a DTES-style composite label) — always resolves via
  point-in-polygon against this file instead.
- **Output location:** `data/raw/cov_open_data/local-area-boundary.csv`.
- **Consumed by:** no longer consumed (`tc_core` uses the GeoJSON export,
  `local-area-boundary.geojson`, instead).
- **Refresh cadence:** rare — official boundaries change infrequently. Last
  fetched 2026-09-18.

---

### `city-owned-properties.csv`

- **What it is:** land the City of Vancouver owns, one row per property
  (`land_coord`, address, local area, holding fund `type`). Counts at the
  2026-09-24 fetch: PROPERTY ENDOWMENT FUND 2,664; CAPITAL FUND 1,170;
  VAHEF (Vancouver Affordable Housing Endowment Fund) 617; Vancouver Public
  Housing Corp 4.
- **Origin and access method:** fetched directly from Open Data by
  `scripts/fetch_cov_open_data.py` (`--only city-owned-properties`).
- **License/attribution:** Open Government Licence – Vancouver.
- **Geographic scope:** citywide.
- **Format/known quirks:** semicolon-separated. `land_coord` is an 8-digit
  key with leading zeros (type inference drops them; the loader pads them
  back). It joins to a building through its folio: a folio's first 8 digits
  are its land coordinate. In the 2026-10-20 build, 226 buildings matched
  (160 of them VAHEF). City land with a private owner on title is a
  leasehold (`classification.owner = mixed`, spec 2026-10-20).
- **Output location:** `raw_city_owned_properties` (`ingest/raw_city_owned.py`).
- **Consumed by:** `metrics/sector.py::city_owned_buildings` (building
  classification).
- **Refresh cadence:** on demand with the other Open Data files.

---

### `business-licences-2013-to-2024.csv`

- **What it is:** the City's historic business licences. Until 2024 long-term
  rentals were licensed by building type (Apartment House, Apartment House
  Strata, Multiple Dwelling, Duplex, Single Detached House, Secondary Suite,
  Rooming House, Pre-1956 Dwelling, 99-year lease); from 2025 they are one
  "Long-term Rental" type. We keep only the 2024 rows of the types the City
  publishes **with addresses**: Apartment House (a building with 3+ dwelling
  units, possibly strata), Rooming House, and 99-year lease. The other types
  are published without addresses. Strata rentals had addresses only in
  2013–2019 (not fetched).
- **Origin and access method:** fetched by `scripts/fetch_cov_open_data.py`
  (`--only business-licences-2013-to-2024`) with a server-side filter
  (`where`/`select`, `fetch/cov_open_data.py::RENTAL_LICENCE_TYPES_2024`);
  licensee names are not fetched.
- **License/attribution:** Open Government Licence – Vancouver.
- **Format/known quirks:** semicolon CSV. Almost every 2024 row has status
  "Inactive" because the year is archived; Cancelled / Gone Out of Business
  are the ones to drop. Match buildings by primary *and* secondary addresses:
  about 10% of licences sit at a building's secondary address.
- **Output location:** `raw_licences_2024` (`ingest/raw_housing_sources.py`).
- **Consumed by:** `metrics/housing.py` (a building's licence type).
- **Refresh cadence:** none needed; the dataset is closed.

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
  `src/tc_core/ingest/overlays.py`. The file came out of a PDF, and text
  extraction damaged some cells: words split ("N on-Profit", "P rivate"), a
  sector label spilled into the operator cell with a stray letter of the
  owner name ("vP rivate", "SPrivate"), and long names cut off ("Atira
  Women's Resourc"). Raw and overlay tables keep the text as published; the
  export reads it through `src/tc_core/sro_text.py` (sector parsing, spilled
  labels become no operator), expands abbreviations via
  `sro_names.py::SRO_NAME_ALIASES`, and applies the reviewed corrections in
  `src/tc_core/sro_names.txt` (committed): cut-off or misspelt names, joint
  owners (`owners: A; B`), the person behind a numbered company
  (`behind: X`, imported as `city_record` claims by
  `scripts/update_sro_claims.py`) and a named lessee (`manager: X`). An SRO
  owner name also reaches its building for landlord-network grouping, like a
  licence holder's name (`metrics/portfolios.py::_sro_owner_addr_keys`).
- **Provenance/original retained:** **not yet** — no original document is
  currently kept. Per the retain-originals convention above, the source
  document(s) this was combined from should be saved under
  `data/raw/cov_foi/` going forward, with a note on how the merge
  was done. TODO once the origin is confirmed.
- **Output location:** `data/raw/cov_foi/sra_housing_combined.csv`.
- **Consumed by:** `tc_core` — raw storage (`ingest/raw_sro.py`) and
  address-key matching onto buildings (`ingest/overlays.py`). 53/171 rows
  (31%, since the 2026-08-07 `secondary_addresses` fallback) match an
  existing building; the rest surface as standalone unmatched markers.
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
  `ingest/overlays.py`). `name` is free text, not a clean address (e.g.
  `"2165-2195 and 2205-2291 W 45th Av (Dunbar Ryerson United Church)"`) —
  parsed by stripping from the first `(`, then splitting on
  `" and "`/`"&"`/`";"` and keying the first fragment. Most rezoning
  applications (churches, single-family lots, commercial, multi-lot
  assemblies) don't correspond to any row in `buildings.csv` at all,
  regardless of parsing quality — ~43/377 (11%) match.
- **Provenance/original retained:** **not yet** — TODO, same as above.
- **Output location:** `data/raw/cov_foi/rezoning_applications.csv`.
- **Consumed by:** `tc_core` — raw storage (`ingest/raw_rezoning.py`)
  and matching (`ingest/overlays.py`), split into open/closed status groups.
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
- **Consumed by:** `tc_core` — raw storage (`ingest/raw_coops.py`) and
  address-key matching (`ingest/overlays.py`). 42/117 rows (36%) match an
  existing building; the rest surface as standalone unmatched markers.
- **Refresh cadence:** periodic, re-run by hand
  (`python scripts/fetch_coops.py`) when a refresh is wanted. 117 co-ops as
  of 2026-08-04 (287 province-wide).

### Landlord listings

- **What it is:** property managers' and landlords' own portfolio listings:
  building name, street address and page URL, plus a status and unit count
  where the feed has them. Tribe Rentals, Dorset Realty Group and MetCap
  Living manage for owners; Wall Financial Corporation owns and runs its own
  buildings.
- **Origin and access:** each company's public website, snapshotted by
  hand. Tribe: theliftsystem.com feed, saved manually. Dorset:
  `scripts/fetch_dorset_listings.py`. Wall: `scripts/fetch_wall_listings.py`.
  MetCap: `scripts/fetch_metcap_listings.py`. Details per company in
  `data/raw/property_managers/MANIFEST.md`.
- **Output location:** `data/raw/property_managers/<company>/<YYYY-MM-DD>.json`
  (gitignored), all in one feed shape.
- **Sensitivity:** feeds can carry staff contact details. Only id, name,
  address, URL, status and unit count are stored (`raw_manager_listings`,
  persistent, with first/last seen per listing); contacts stay in the raw file.
- **Consumed by:** `tc_core`, using only *usable* listings: those in the
  company's latest snapshot and not "In Development"/"Coming Soon"
  (`ingest/manager_listings.py::usable_listings`).
  - Building names (`ingest/building_names.py`).
  - A "Listed by <company> ↗" link on every listed building
    (`building_listings`, the export's `listings` column).
  - `managed_by` for companies in `data/curated/property_managers.toml`
    (`listing_names` maps a feed's name to the toml's). Listings never set
    the owner.
  - New buildings: a listing that matches no City-source building but sits on
    a City address point adds one, with building source "manager listing" and
    owner "(Unknown)" (`ingest/listing_buildings.py`). The rebuild prints each
    one for review.
- **Refresh cadence:** re-run the scripts (and save Tribe's feed) when a
  refresh is wanted, then rebuild. 2026-09-30: Dorset 50 (39 Vancouver),
  Wall 18, MetCap 23 Vancouver; 7 buildings added from listings.

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
  never committed. `raw_lotr_ownership` in `data/derived/tc_core.db` (also
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
  becoming claims. The public export also lists each building's interest
  holders (`metrics/registry_owners.py::build_interest_holders`): rows typed
  `INTEREST_HOLDER`, `RB_TRUSTEE_*`, `RB_TRUST_SETTLOR_*` or `RB_PARTNER_*`
  whose holder isn't the reporting body itself, published as name, interest
  type and PIDs only — that query reads no residence, citizenship or address
  column.
- **Provenance/original retained:** locally only — see Sensitivity above.
  `raw_lotr_ownership` stores the export verbatim in SQLite for
  browsability (see `ingest/raw_lotr.py`), but that database is itself
  gitignored, same as the source CSV.
- **Output location:** `data/raw/samwise/samwise-export.csv` (gitignored,
  local-only — see Sensitivity above).
- **Consumed by:** `tc_core` only — `ingest/raw_lotr.py` (raw storage)
  and `ingest/lotr_claims.py` (derives `common_owner` `ownership_claims`
  from shared beneficial-interest holders). Not wired into the main `run_ingest()` pipeline — imported
  standalone via `scripts/import_lotr_claims.py`.
- **Refresh cadence:** ad hoc, whenever `samwise` produces a new export —
  re-run `scripts/import_lotr_claims.py` to pick it up.

---

## Internal / organizational

### VTU membership (NationBuilder) — retired 2026-10-20

VTU's NationBuilder membership export (`data/raw/nationbuilder/membership_full.csv`,
154 columns of personal data) used to be ingested, allow-listed down to an ID,
address, tags and update date, into a `vtu_membership` table, and joined to
buildings by address. Nothing public ever used it, so it was removed from the
pipeline: the database feeding the public map holds no membership data at all.
If an internal tool needs it later, it gets its own store, joined by `addr_key`.
The old ingest is in git history (`src/tc_core/ingest/membership.py`).

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
6. If it lands in `data/` as a plain CSV meant for `tc_core`, add a
   corresponding `ingest/raw_<source>.py` module following the existing
   pattern (explicit column allow-list, raise on unexpected columns) — see
   [Scope](#scope) above for why that's not re-described in this doc.
