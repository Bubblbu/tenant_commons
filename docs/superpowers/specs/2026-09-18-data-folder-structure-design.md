# Data folder structure — design

Status: draft for review · 2026-09-18

## Goal

Restructure `data/` so the layout shows where each file comes from and how it is processed, and fold the parts of the `vhd` pipeline this repo needs into this repo so `vhd` can be retired.

Nothing under `data/` is tracked by git any more, except `README.md` and per-source `MANIFEST.md` files.

## Layout

```
data/
├── README.md                     # tracked: stage rules, ignore policy
├── raw/                          # as received; never hand-edited
│   ├── cov_open_data/            # fetched by script
│   │   ├── MANIFEST.md
│   │   ├── local-area-boundary
│   │   ├── property-addresses
│   │   ├── property-tax-report   (refine report_year)
│   │   ├── business-licences
│   │   ├── non-market-housing
│   │   ├── rental-standards-current-issues
│   │   ├── block-outlines
│   │   └── block-numbers
│   ├── cov_foi/                  # manual
│   │   ├── MANIFEST.md
│   │   ├── FOI 2023-186 PDF + extracted CSV (all_rentals.2023-186.csv)
│   │   ├── FOI 2024-698 PDF + extracted CSV
│   │   ├── sra_housing_combined.csv        (origin unverified)
│   │   └── rezoning_applications.csv       (origin unverified)
│   ├── vanmaps/                  # manual: addresses.geojson (primary/secondary resolution)
│   ├── chf_bc/                   # fetched: coops_vancouver.csv + saved HTML
│   ├── nationbuilder/            # manual, private: membership_full.csv
│   └── samwise/                  # manual, private: samwise-export.csv
├── curated/                      # hand-authored
│   ├── ownership_claims.csv
│   ├── landlord_mapping.toml     # moved from vhd, logic unchanged
│   └── chinatown_boundary.geojson
├── derived/                      # regenerable by scripts
│   ├── interim/                  # all_rentals.csv, properties.csv
│   ├── buildings.csv             # output of the ported build, no longer a raw source
│   ├── ct_properties.csv         # Chinatown property list
│   ├── vtu_membership_public.csv
│   ├── pid_address_map.csv
│   └── sica_core.db
└── exports/                      # what leaves the pipeline (structure unchanged from today's public feed)
```

Flow: `raw/` + `curated/` → `derived/` (interim → buildings → db) → `exports/`.

## Git policy

`.gitignore` ignores everything under `data/` and re-includes `README.md` and `**/MANIFEST.md`. Verify the negation pattern with `git check-ignore` (git cannot re-include a file inside an ignored directory, so the directory pattern must be `data/**` with `!data/**/` for traversal).

Files currently tracked are untracked with `git rm --cached`. This does not remove them from history.

Because `ownership_claims.csv` and `landlord_mapping.toml` stop having a git history, they need a manual backup until the provenance/publishing decision is made.

## Manifests

One `MANIFEST.md` per source directory. Per file: source and URL, fetch date, method (scripted / copied / manual with exact steps), row count, license. `docs/DATA_SOURCES.md` keeps the detailed per-source reference and links to the manifests.

## Pipeline changes (port, not rewrite)

Source of the logic: `~/Projects/VTU/vancouver-housing-data` (`vhd`).

| Piece | From | To |
|---|---|---|
| Open Data fetch | `vhd/src/vhd/api.py`, `yvr_open_data.toml` (11 datasets) | one fetch script, 8 datasets (the 6 used by `vhd` plus `block-outlines` and `block-numbers`, both confirmed as Open Data datasets) → `raw/cov_open_data/` |
| FOI merge | `merge_foi_releases.py` | prepare step → `derived/interim/all_rentals.csv` |
| Properties | `build_properties.py` | prepare step → `derived/interim/properties.csv` (incl. Chinatown flag, using `curated/chinatown_boundary.geojson`) |
| Buildings | `build_buildings.py` | prepare step → `derived/buildings.csv`, `derived/ct_properties.csv` |
| Landlord mapping | `landlord_mapping.toml` | `curated/`, read by the buildings step exactly as today |

- **Business logic is unchanged.** `bsns_group` assignment, the `Long-term Rental` filter, address cleaning and the joins keep their current behavior. The only code edit is consolidating the three copies of `clean_address` into one.
- **FOI 2023:** the PDF-to-CSV step (`process_foi_release.py`, needs `tabula`/Java) is not ported. The already-extracted `all_rentals.2023-186.csv` is treated as a manually extracted raw file, like the 2024 one; steps recorded in the manifest.
- **Format:** each dataset is fetched in the formats its consumers read, so neither reader has to change. The ingest reads the semicolon CSVs (`property-addresses`, `local-area-boundary`, `block-outlines`, `block-numbers`); the prepare steps read GeoJSON (`property-addresses`, `local-area-boundary`, `property-tax-report`, `business-licences`, `non-market-housing`, `rental-standards-current-issues`). `property-addresses` and `local-area-boundary` are therefore fetched in both.
- `sync_from_vhd.py` is replaced by the fetch script.
- `config.toml` paths and hard-coded defaults (`sica_core/config.py`, `fetch_coops.py`, ingest docstrings, `DATA_SOURCES.md`) are updated to the new layout.

## Known data issue this fixes

`data/property_addresses.csv` and `data/local-area-boundary.csv` are byte-identical to `vhd`'s 2024-03-08 CSV exports; only the geojson files were refreshed in 2026. `buildings.csv` was built from 2026 data, so `raw_addresses` and `pid_address_map.csv` are a vintage older than `buildings.csv`. Fetching directly from Open Data removes the mismatch. After the fetch, rebuild the db and compare row counts against the old one.

## Migration order

1. Create folders, manifests and the ignore policy. Move files with `mv`, then untrack.
2. Update `config.toml` and default paths so the existing pipeline runs on the new layout.
3. Port the fetch and prepare scripts; re-fetch Open Data.
4. Rebuild `sica_core.db`; diff row counts against the previous db (per the diff-validate pattern).
5. Archive `vhd` and `vancouver-housing-data-dir` to a tarball outside the repo (neither is under git), then retire them.

## Retired with `vhd`

Notebooks, `processing_pipeline/`, `.bak` files, packaging files, `helpers.py`, `models/addresses.py`, the unused `business_mappings` dict, the 5 unused Open Data downloads (parcel polygons, tie lines, building permits, city-owned properties, heritage sites), the strata CSV, and `sync_from_vhd.py`.

## Out of scope / deferred

- Claims provenance and publishing.
- Diffs and vintage records for raw pulls.
- Landlord grouping and portfolio mechanism (`landlord_mapping.toml` versus `common_owner` claims).
- Rebuilding the buildings assembly as separate `raw_*` tables in `sica_core`.
- Named, on-demand export views (declarative view definitions, per-export manifests, tiering).
- Chinatown boundary layer and toggle on the public map. The data side is only the boundary file in `curated/`.
