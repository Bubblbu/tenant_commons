# SICA Mapping

SICA Mapping is a map and data toolchain for VTU (Vancouver Tenants Union) organizers.
It has two halves. `sica_core` is a Python data package: it ingests the public and
internal sources into SQLite and exports a versioned artifact directory. `frontend/` is a
Vite + TypeScript Leaflet map that reads only that directory and derives no data itself.

See [`CLAUDE.md`](CLAUDE.md) §3 for the data model and pipeline.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `src/sica_core/` | The backend: ingest, overlay matching, claims, and the artifact export. |
| `scripts/rebuild_map.py` | Ingest + export: rebuilds the SQLite store and writes the artifacts. |
| `frontend/` | The map (Vite + TypeScript). See [`frontend/README.md`](frontend/README.md). |
| `data/derived/artifacts/` | The contract between the two halves (gitignored). |
| `config.toml` | Input, database, and artifact paths. |
| `data/` | Local sources and derived output (not committed; see [`data/README.md`](data/README.md)). |

## Requirements

- Backend: Python 3.12+ and `uv`.
- Frontend: Node 24 (`frontend/.nvmrc`).

Each half needs only its own toolchain.

## Installation

Using [uv](https://github.com/astral-sh/uv):

```bash
uv sync
source .venv/bin/activate
```

Frontend:

```bash
cd frontend && npm ci
```

## Input Data Expectations

The pipeline expects three CSV files, with paths set in `config.toml` under `[paths]`.

| `config.toml` key | Example file | Required columns |
| --- | --- | --- |
| `buildings` | `data/derived/buildings.csv` | At minimum `address`, `local_area`, `units`, `year_built`, `value_land`, `value_bldg`, VTU-friendly ownership columns such as `bsns_group`. |
| `addresses` | `data/raw/cov_open_data/property-addresses.csv` | `civic_number`, `std_street`, and `geo_point_2d` (containing `"lat,lon"`). Optional `local_area_*` columns improve enrichment. |
| `blocks` | `data/raw/cov_open_data/block-outlines.csv` | Polygon GeoJSON in a `geom` column and any block metadata you want surfaced in tables. |

Keeping the suggested column names avoids surprises.

## Building the map

Rebuild order (details in [`data/README.md`](data/README.md)):

```bash
uv run python scripts/fetch_cov_open_data.py                    # raw/cov_open_data
uv run python scripts/prepare_data.py                           # derived/interim, derived/buildings.csv
uv run python -m sica_core.ingest --config config.toml          # derived/sica_core.db
uv run python scripts/export_pid_address_map.py                 # derived/pid_address_map.csv
uv run python scripts/rebuild_map.py                            # derived/artifacts (the frontend's input)
cd frontend && npm ci && npm run build                          # frontend/dist
```

For development, `cd frontend && npm run dev` serves the map with hot reload. See
[`frontend/README.md`](frontend/README.md) for configuration.

## Development Workflow

- `uv run python scripts/rebuild_map.py [--skip-ingest]` when data or export logic
  changes (`--skip-ingest` re-exports from the existing database).
- `npm run dev` (hot reload) for everything in `frontend/`.
- `uv run pytest` and `npm test` (in `frontend/`) run the two test suites.

## Branching & Deployment

Two long-lived branches (GitHub Flow + a release branch):

| Branch | Role |
| --- | --- |
| `main` | Integration. Always green, always deployable. **Not** auto-deployed. All feature PRs target it. |
| `production` | What should be live. Deploy is currently **disabled** (`deploy.yml` has no push trigger) until design spec §11 decides how it gets real artifacts. |

### Everyday work

1. Branch off `main`, open a PR back into `main`.
2. `.github/workflows/ci.yml` runs two jobs on the PR: **backend** (pytest; ruff advisory) and **frontend** (type check, unit tests, and a build against `frontend/fixtures/`).
3. Merge once CI is green.

### Releasing (promoting to the live site)

*Paused while deploy is disabled (spec §11).*

1. Open a PR **from `main` into `production`**. The diff is your release notes.
2. Merge it. `deploy.yml` fires on the push to `production` and updates GitHub Pages.
3. Tag the merge commit (`git tag -a v0.x.0 -m "…" && git push --tags`).

`workflow_dispatch` is kept on `deploy.yml` for a manual re-deploy of whatever
is currently on `production`.

### One-time GitHub setup (repo admin, in Settings → Branches)

- Protect `main`: require a PR, require the `backend` and `frontend` checks to pass, disallow direct pushes.
- Protect `production`: require a PR (restrict its source to `main`), require the `backend` and `frontend` checks to pass,
  require linear history, disallow direct pushes, restrict who can merge.

## To-dos

### Mapping

- [ ] Add export feature
- [ ] Integrate more useful data sources
- [ ] Deep overhaul of tool for performance

### Overall

- [ ] Rethink deployment process
