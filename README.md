# Tenant Commons

Tenant Commons is a map and data toolchain for VTU (Vancouver Tenants Union) organizers.
It has two halves. `tc_core` is a Python data package: it ingests the public and
internal sources into SQLite and exports a versioned artifact directory. `frontend/` is a
Vite + TypeScript Leaflet map that reads only that directory and derives no data itself.

See [`CLAUDE.md`](CLAUDE.md) §3 for the data model and pipeline.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `src/tc_core/` | The backend: ingest, overlay matching, claims, and the artifact export. |
| `scripts/rebuild_data.py` | Ingest + export: rebuilds the SQLite store and writes the artifacts. |
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

The pipeline reads several source files, most set in `config.toml` under `[paths]`. These three are the minimum to get a build going:

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
uv run python -m tc_core.ingest --config config.toml            # derived/tc_core.db
uv run python scripts/export_pid_address_map.py                 # derived/pid_address_map.csv
uv run python scripts/rebuild_data.py                           # derived/artifacts (the frontend's input)
cd frontend && npm ci && npm run build                          # frontend/dist
```

For development, `cd frontend && npm run dev` serves the map with hot reload. See
[`frontend/README.md`](frontend/README.md) for configuration.

## Development Workflow

- `uv run python scripts/rebuild_data.py [--skip-ingest]` when data or export logic
  changes (`--skip-ingest` re-exports from the existing database).
- `npm run dev` (hot reload) for everything in `frontend/`.
- `uv run pytest` and `npm test` (in `frontend/`) run the two test suites.

## Branching & Deployment

Two branches, two different kinds of thing:

| Branch | Role |
| --- | --- |
| `main` | Integration. Always green. All feature PRs target it. |
| `production` | **Not source.** A snapshot of `frontend/dist`, pushed wholesale on release. Never has its own commits or PRs — GitHub Pages serves it directly, no CI involved. |

### Everyday work

1. Branch off `main`, open a PR back into `main`.
2. `.github/workflows/ci.yml` runs two jobs on the PR: **backend** (pytest; ruff advisory) and **frontend** (type check, unit tests, and a build against `frontend/fixtures/`).
3. Merge once CI is green.

### Releasing (promoting to the live site)

`production` holds a *built* snapshot, not source, so there is no merge and nothing to conflict — each
release overwrites it wholesale.

1. If the data changed, rebuild it: `uv run python scripts/rebuild_data.py`.
2. From `frontend/`: `npm run deploy`. This runs `vite build` against your real local artifacts, then
   force-pushes `dist/`'s contents as the entirety of the `production` branch via
   [`gh-pages`](https://www.npmjs.com/package/gh-pages) — nothing to review, nothing to merge.
3. GitHub Pages picks it up automatically (Settings → Pages → "Deploy from a branch" → `production` / `(root)`).
4. Optionally tag the release, on `main` (not `production` — it has no meaningful commit history):
   `git tag -a v0.x.0 -m "…" && git push --tags`.

The custom domain (`frontend/public/CNAME`) is copied into every build automatically, so it survives each
overwrite without a manual step.

### One-time GitHub setup (repo admin, in Settings → Branches / Pages)

- Protect `main`: require a PR, require the `backend` and `frontend` checks to pass, disallow direct pushes.
- `production` needs **no** branch protection — nothing is ever committed to it except full `npm run deploy`
  overwrites, and it's never a PR target.
- Settings → Pages: source = "Deploy from a branch", branch = `production`, folder = `/ (root)`. Set the
  custom domain and enable "Enforce HTTPS" once DNS has propagated.

## To-dos

### Mapping

- [ ] Integrate more useful data sources
- [ ] Deep overhaul of tool for performance
