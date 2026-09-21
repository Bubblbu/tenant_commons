# data/

Everything under `data/` is ignored by git except this README and the
`MANIFEST.md` files. Nothing here is a source of truth for git history.

| Folder | Meaning |
|---|---|
| `raw/` | As received from the source. Never hand-edited. One folder per source, each with a `MANIFEST.md`. |
| `curated/` | Hand-authored: `ownership_claims.csv`, `landlord_mapping.toml`, `chinatown_boundary.geojson`. No backup in git — keep your own copy. |
| `derived/` | Regenerable by scripts; safe to delete and rebuild. Includes the SQLite db. |
| `exports/` | Reserved for what leaves the pipeline. Today the map feed still goes to `.preprocessed/` and `www/`. |

## Rebuild order

```bash
uv run python scripts/fetch_cov_open_data.py                    # raw/cov_open_data
uv run python scripts/prepare_data.py                           # derived/interim, derived/buildings.csv
uv run python scripts/build_vtu_public_extract.py               # derived/vtu_membership_public.csv (needs raw/nationbuilder)
uv run python -m sica_core.ingest --config config.toml          # derived/sica_core.db
uv run python scripts/export_pid_address_map.py                 # derived/pid_address_map.csv
uv run python scripts/rebuild_map.py                            # derived/artifacts (the frontend's input)
```

Ingest always needs `raw/cov_open_data/local-area-boundary.geojson` (fetched
by the first step): its overlays step resolves neighbourhoods for co-op/SRO
records with it, and fails the run if the file is missing.

Sources without a fetch script (FOI, VanMaps, NationBuilder, Samwise) are
manual: see each folder's `MANIFEST.md` for what to put there. The co-op list
refreshes with `uv run python scripts/fetch_coops.py`, and claims are imported
with `uv run python scripts/update_claims.py` (ownership_claims.csv) and
`uv run python scripts/import_lotr_claims.py` (raw/samwise).
