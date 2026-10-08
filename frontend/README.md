# Tenant Commons map frontend

A Vite + TypeScript project that renders the map from `tc_core`'s artifact
directory. It reads nothing else: no CSV, no SQLite, no Python.

## Toolchains

Only this half needs Node (version in `.nvmrc`, currently 24 LTS). The backend
(`tc_core`, `uv`) is only needed to *produce* artifacts; a checkout can build
the frontend against `fixtures/` with Node alone.

## Artifacts

`TC_ARTIFACTS_DIR` names the artifact directory (default
`../data/derived/artifacts`, produced by `uv run python scripts/rebuild_data.py`
from the repo root). It is served at `/data/` by `npm run dev` and copied into
`dist/data/` by `npm run build`. Contract: `filter_config.json`,
`marker_metadata.json`, `building_records.json`, `networks.json` and
`blocks.geojson` each carry `schema_version` (checked at load);
`local-area-boundary.geojson` is the City's file, passed through.
`building_records.json` and `networks.json` follow `tc_core/contract.py`; their
TypeScript types (`src/contract.gen.ts`) are generated from
`src/contract.schema.json` with `npm run gen:types` (regenerate the schema
first with `uv run python scripts/write_contract_schema.py`). Tables, filters
and the CSV export read a flat view of each building (`src/flat.ts`); the popup
(`src/popup/`) reads the nested record.

## Commands

```bash
npm ci                                      # install (pinned by package-lock.json)
npm run dev                                 # dev server with hot reload
npm run build                               # dist/, including dist/data/
TC_ARTIFACTS_DIR=fixtures npm run build   # build against the synthetic fixtures
npm run preview                             # serve dist/
npm test                                    # unit tests (Vitest)
npm run typecheck                           # tsc --noEmit
```
