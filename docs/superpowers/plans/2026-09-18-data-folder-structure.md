# Data Folder Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `data/` into `raw/ curated/ derived/ exports/`, untrack everything under it except a README and per-source manifests, and absorb the parts of the `vhd` pipeline this repo needs so `vhd` can be retired.

**Architecture:** A single `DataPaths` class in `sica_core` defines the layout; `config.toml` and the ingest keep working by pointing at the new paths. The `vhd` scripts are ported into `sica_core/prepare/` as functions (business logic untouched) and validated by replaying them against `vhd`'s own 2026-08-07 inputs and diffing against its outputs. A new fetcher pulls the Open Data files directly, replacing `sync_from_vhd.py` and fixing the stale 2024 address CSVs.

**Tech Stack:** Python 3.12, uv, pytest, pandas (ingest), polars + geopandas (ported prepare steps), requests (fetch), sqlite3.

**Spec:** `docs/superpowers/specs/2026-09-18-data-folder-structure-design.md`

## Global Constraints

- Nothing under `data/` is tracked by git except `data/README.md` and `data/**/MANIFEST.md` (spec, "Git policy").
- **Business logic is unchanged**: `bsns_group` assignment, the `Long-term Rental` filter, address cleaning and the joins keep their current behavior. The only intended code edits to ported logic are consolidating the three copies of `clean_address` into one, removing writes of outputs nothing reads, and the FOI merge reading its 2023 input from a raw file instead of overwriting it in place (see Task 5).
- Flow: `raw/` + `curated/` → `derived/` (interim → buildings → db) → `exports/`. `exports/` is created but not wired: the map feed still goes to `.preprocessed/` and `www/`, unchanged.
- The FOI 2023 PDF-to-CSV step (`tabula`/Java) is **not** ported; `all_rentals.2023-186.csv` is a manually extracted raw file.
- The fetcher covers 8 datasets: `local-area-boundary`, `property-addresses`, `property-tax-report` (refine `report_year:<year>`), `business-licences`, `non-market-housing`, `rental-standards-current-issues`, `block-outlines`, `block-numbers`. Each is fetched in the formats its consumers read (CSV for ingest, GeoJSON for the prepare steps).
- Deferred, do not touch: claims provenance/publishing, diffs/vintage records, `landlord_mapping.toml` vs `common_owner` claims, rebuilding the buildings assembly as `raw_*` tables, named export views, the Chinatown map layer.
- **Project rules:** never run git commands that change state (`commit`, `rm --cached`, `add`, etc.) without asking the user first; never add Claude attribution to commits or PR text. Every "Commit" step below is a *proposal*, executed only after the user says yes.
- `ownership_claims.csv` and `landlord_mapping.toml` have no git history once untracked. Task 1's backup is the only safety net until the provenance decision is made.
- `SCRATCH=/tmp/claude-1000/-home-asura-Projects-VTU-map-explorer/bab789d5-8c42-4af2-a288-23308a628d04/scratchpad` is used for temporary files. Run all commands from `/home/asura/Projects/VTU/map_explorer` unless stated.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/sica_core/paths.py` (create) | `DataPaths`: the one definition of the data layout | 2 |
| `tests/test_data_layout.py` (create) | Layout constants + `config.toml` consistency | 2 |
| `config.toml`, `src/sica_core/config.py`, `scripts/fetch_coops.py` (modify) | Point at the new layout | 2 |
| `.gitignore` (modify) | Ignore policy | 2 |
| `data/raw/cov_foi/*`, `data/raw/vanmaps/*`, `data/curated/*` (copy) | vhd's manual inputs and curated files | 3 |
| `src/sica_core/prepare/address.py` (create) | `clean_address`, `fix_street_names` (single copy) | 4 |
| `src/sica_core/prepare/io.py` (create) | `load_polars` GeoJSON loader | 4 |
| `src/sica_core/prepare/foi.py` (create) | FOI 2023 + 2024 merge | 5 |
| `src/sica_core/fetch/cov_open_data.py`, `scripts/fetch_cov_open_data.py` (create) | Open Data download plan + downloader + CLI | 6 |
| `src/sica_core/prepare/properties.py`, `buildings.py`, `scripts/prepare_data.py` (create) | Ported `build_properties.py`, `build_buildings.py` + CLI | 7 |
| (run only) | First real refresh and validation | 8 |
| `data/README.md`, `data/raw/*/MANIFEST.md` (create); `docs/DATA_SOURCES.md`, `CLAUDE.md`, docstrings (modify) | Tracked documentation, stale paths | 9 |
| `scripts/sync_from_vhd.py` (delete), vhd directories (delete after confirmation) | Retirement | 10 |

---

### Task 1: Preflight backups (no repo changes)

**Files:** none in the repo. Creates `~/Projects/VTU/_archive/2026-09-18-data-restructure/`.

**Interfaces:**
- Produces: the archive directory. Task 10 verifies it before anything is deleted.

- [ ] **Step 1: Confirm the archive location is outside every git repo**

```bash
git -C ~/Projects/VTU rev-parse --show-toplevel 2>&1 | head -1
```
Expected: `fatal: not a git repository`. If it prints a path, choose a different `BK` outside any repo.

- [ ] **Step 2: Create the archive**

```bash
BK=~/Projects/VTU/_archive/2026-09-18-data-restructure
mkdir -p "$BK"
tar czf "$BK/vancouver-housing-data.tgz" -C ~/Projects/VTU --exclude='vancouver-housing-data/.venv' vancouver-housing-data
tar czf "$BK/vancouver-housing-data-dir.tgz" -C ~/Projects/VTU vancouver-housing-data-dir
cp -a data "$BK/map_explorer-data"
```

- [ ] **Step 3: Verify the archive**

```bash
tar tzf "$BK/vancouver-housing-data.tgz" | grep -c landlord_mapping.toml
tar tzf "$BK/vancouver-housing-data-dir.tgz" | grep -c 'processed/buildings.csv'
md5sum data/ownership_claims.csv "$BK/map_explorer-data/ownership_claims.csv"
ls "$BK"
```
Expected: `1`, `1`, two identical md5 lines, and three entries listed.

- [ ] **Step 4: Ask the user to copy `ownership_claims.csv` and `landlord_mapping.toml` to somewhere durable** (cloud or another disk). The archive is on the same disk. Do not proceed to Task 2 until they confirm or explicitly decline.

---

### Task 2: Layout, ignore policy and `DataPaths`, with the pipeline repointed

**Files:**
- Create: `src/sica_core/paths.py`
- Create: `tests/test_data_layout.py`
- Modify: `config.toml`, `src/sica_core/config.py:20`, `scripts/fetch_coops.py:30`, `.gitignore`

**Interfaces:**
- Produces: `sica_core.paths.DataPaths(root="data")` with attributes (all `pathlib.Path`):
  `root, raw, curated, derived, interim, exports, cov_open_data, cov_foi, vanmaps, chf_bc, nationbuilder, samwise`, and
  `property_addresses_csv, local_area_boundary_csv, block_outlines_csv, block_numbers_csv, sro_housing, rezoning_applications, coops, membership_full, samwise_export, ownership_claims, landlord_mapping, chinatown_boundary, vanmaps_addresses, foi_2023_extract, foi_2024_extract, all_rentals, properties, buildings, ct_properties, vtu_public, pid_address_map, db`,
  and the method `cov(dataset: str, fmt: str) -> Path` returning `cov_open_data / f"{dataset}.{fmt}"`.
  Tasks 3–9 use these names exactly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_data_layout.py`:

```python
"""Guards the data/ layout: DataPaths is the single definition, and
config.toml's [paths] must agree with it (both are read by different code)."""

import tomllib
from pathlib import Path

from sica_core.paths import DataPaths

REPO_ROOT = Path(__file__).resolve().parent.parent

# config.toml [paths] key -> DataPaths attribute
CONFIG_KEYS = {
    "buildings": "buildings",
    "addresses": "property_addresses_csv",
    "blocks": "block_outlines_csv",
    "block_numbers": "block_numbers_csv",
    "local_area_boundary": "local_area_boundary_csv",
    "vtu": "vtu_public",
    "vtu_raw": "membership_full",
    "sica_core_db": "db",
    "pid_address_map": "pid_address_map",
    "sro_housing": "sro_housing",
    "rezoning_applications": "rezoning_applications",
    "coops": "coops",
    "ownership_claims": "ownership_claims",
    "lotr_ownership": "samwise_export",
}


def test_layout_stages():
    p = DataPaths("data")
    assert p.property_addresses_csv == Path("data/raw/cov_open_data/property-addresses.csv")
    assert p.cov("property-tax-report", "geojson") == Path(
        "data/raw/cov_open_data/property-tax-report.geojson"
    )
    assert p.ownership_claims == Path("data/curated/ownership_claims.csv")
    assert p.landlord_mapping == Path("data/curated/landlord_mapping.toml")
    assert p.all_rentals == Path("data/derived/interim/all_rentals.csv")
    assert p.buildings == Path("data/derived/buildings.csv")
    assert p.db == Path("data/derived/sica_core.db")


def test_root_is_configurable(tmp_path):
    p = DataPaths(tmp_path)
    assert p.buildings == tmp_path / "derived" / "buildings.csv"


def test_config_toml_matches_layout():
    cfg = tomllib.loads((REPO_ROOT / "config.toml").read_text())["paths"]
    p = DataPaths("data")
    for key, attr in CONFIG_KEYS.items():
        assert Path(cfg[key]) == getattr(p, attr), key
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data_layout.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'sica_core.paths'`.

- [ ] **Step 3: Create `DataPaths`**

Create `src/sica_core/paths.py`:

```python
"""The data/ layout, defined once.

Stages: raw/ (as received, never hand-edited) + curated/ (hand-authored)
-> derived/ (regenerable) -> exports/ (what leaves the pipeline).
config.toml's [paths] is read by the ingest and by sica_mapping; a test
(tests/test_data_layout.py) keeps it in agreement with this class.
"""

from __future__ import annotations

from pathlib import Path


class DataPaths:
    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)
        self.raw = self.root / "raw"
        self.curated = self.root / "curated"
        self.derived = self.root / "derived"
        self.interim = self.derived / "interim"
        self.exports = self.root / "exports"

        # raw/ sources
        self.cov_open_data = self.raw / "cov_open_data"
        self.cov_foi = self.raw / "cov_foi"
        self.vanmaps = self.raw / "vanmaps"
        self.chf_bc = self.raw / "chf_bc"
        self.nationbuilder = self.raw / "nationbuilder"
        self.samwise = self.raw / "samwise"

        self.property_addresses_csv = self.cov("property-addresses", "csv")
        self.local_area_boundary_csv = self.cov("local-area-boundary", "csv")
        self.block_outlines_csv = self.cov("block-outlines", "csv")
        self.block_numbers_csv = self.cov("block-numbers", "csv")

        self.foi_2023_extract = self.cov_foi / "all_rentals.2023-186.csv"
        self.foi_2024_extract = self.cov_foi / "2024-698_extracted_data.csv"
        self.sro_housing = self.cov_foi / "sra_housing_combined.csv"
        self.rezoning_applications = self.cov_foi / "rezoning_applications.csv"

        self.vanmaps_addresses = self.vanmaps / "addresses.geojson"
        self.coops = self.chf_bc / "coops_vancouver.csv"
        self.membership_full = self.nationbuilder / "membership_full.csv"
        self.samwise_export = self.samwise / "samwise-export.csv"

        # curated/
        self.ownership_claims = self.curated / "ownership_claims.csv"
        self.landlord_mapping = self.curated / "landlord_mapping.toml"
        self.chinatown_boundary = self.curated / "chinatown_boundary.geojson"

        # derived/
        self.all_rentals = self.interim / "all_rentals.csv"
        self.properties = self.interim / "properties.csv"
        self.buildings = self.derived / "buildings.csv"
        self.ct_properties = self.derived / "ct_properties.csv"
        self.vtu_public = self.derived / "vtu_membership_public.csv"
        self.pid_address_map = self.derived / "pid_address_map.csv"
        self.db = self.derived / "sica_core.db"

    def cov(self, dataset: str, fmt: str) -> Path:
        """A file fetched from Vancouver Open Data, e.g. cov('block-numbers', 'csv')."""
        return self.cov_open_data / f"{dataset}.{fmt}"
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_data_layout.py -v`
Expected: `test_layout_stages` and `test_root_is_configurable` PASS; `test_config_toml_matches_layout` FAILS (config.toml still has the old paths). That failure is what the next steps fix.

- [ ] **Step 5: Move the files**

Make sure LibreOffice has no file open in `data/` first (the lock file `.~lock.sra_housing_combined.csv#` is a stray, safe to delete once nothing has it open).

```bash
mkdir -p data/raw/{cov_open_data,cov_foi,vanmaps,chf_bc,nationbuilder,samwise} \
         data/curated data/derived/interim data/exports
mv data/property_addresses.csv   data/raw/cov_open_data/property-addresses.csv
mv data/local-area-boundary.csv  data/raw/cov_open_data/local-area-boundary.csv
mv data/block-outlines.csv       data/raw/cov_open_data/block-outlines.csv
mv data/block-numbers.csv        data/raw/cov_open_data/block-numbers.csv
mv data/sra_housing_combined.csv data/raw/cov_foi/
mv data/rezoning_applications.csv data/raw/cov_foi/
mv data/coops_vancouver.csv      data/raw/chf_bc/
mv data/Nationbuilder/* data/raw/nationbuilder/ && rmdir data/Nationbuilder
mv data/Samwise/*       data/raw/samwise/       && rmdir data/Samwise
mv data/ownership_claims.csv     data/curated/
mv data/buildings.csv data/vtu_membership_public.csv data/pid_address_map.csv data/sica_core.db data/derived/
rm -f 'data/.~lock.sra_housing_combined.csv#'
find data -maxdepth 3 -type f | sort
```
Expected: every file listed under `raw/`, `curated/` or `derived/`; nothing left directly in `data/`.

- [ ] **Step 6: Repoint `config.toml`**

Replace the whole `[paths]` table (leave `[options]` as is):

```toml
# config.toml
[paths]
buildings = "data/derived/buildings.csv"
addresses = "data/raw/cov_open_data/property-addresses.csv"
blocks = "data/raw/cov_open_data/block-outlines.csv"
block_numbers = "data/raw/cov_open_data/block-numbers.csv"
local_area_boundary = "data/raw/cov_open_data/local-area-boundary.csv"
vtu = "data/derived/vtu_membership_public.csv"
# Raw NationBuilder export, gitignored (see data/raw/nationbuilder/) — used only by
# sica_core's internal-tool ingest, never by the public sica_mapping build above.
vtu_raw = "data/raw/nationbuilder/membership_full.csv"
sica_core_db = "data/derived/sica_core.db"
pid_address_map = "data/derived/pid_address_map.csv"
sro_housing = "data/raw/cov_foi/sra_housing_combined.csv"
rezoning_applications = "data/raw/cov_foi/rezoning_applications.csv"
coops = "data/raw/chf_bc/coops_vancouver.csv"
ownership_claims = "data/curated/ownership_claims.csv"
lotr_ownership = "data/raw/samwise/samwise-export.csv"
```

- [ ] **Step 7: Repoint the hard-coded defaults**

In `src/sica_core/config.py` change `DEFAULT_DB_PATH = "data/sica_core.db"` to `DEFAULT_DB_PATH = "data/derived/sica_core.db"`.

In `scripts/fetch_coops.py` change `DEFAULT_OUT = "data/coops_vancouver.csv"` to `DEFAULT_OUT = "data/raw/chf_bc/coops_vancouver.csv"`. Then run `grep -n "sources" scripts/fetch_coops.py`; if it saves retained HTML under `data/sources/...`, change that path to `data/raw/chf_bc/`.

- [ ] **Step 8: Set the ignore policy**

In `.gitignore`, delete the lines `data/sica_core.db`, `data/Nationbuilder/*` and `data/Samwise/*` (keep `docs/disambiguation/*`), and put this block in their place:

```gitignore
# Everything under data/ is ignored; only the README and per-source manifests
# are tracked. Membership exports are personal data — must never be committed.
data/**
!data/README.md
!data/**/
!data/**/MANIFEST.md
```

Verify with a dry run (create two throwaway files first):

```bash
touch data/README.md data/raw/cov_open_data/MANIFEST.md
git add -n data/
rm data/README.md data/raw/cov_open_data/MANIFEST.md
```
Expected output is exactly two lines: `add 'data/README.md'` and `add 'data/raw/cov_open_data/MANIFEST.md'`. If any CSV, `.db` or the Nationbuilder/Samwise files appear, the ignore pattern is wrong; stop and fix it before continuing.

- [ ] **Step 9: Run the tests**

Run: `uv run pytest -q`
Expected: 10 passed (7 existing + 3 new).

- [ ] **Step 10: Verify the pipeline still runs on the new layout**

Ingest into a *copy* of the database. `ownership_claims` and `ingest_runs` live in the db and must never be dropped, so never point a test ingest at the real one.

```bash
SCRATCH=/tmp/claude-1000/-home-asura-Projects-VTU-map-explorer/bab789d5-8c42-4af2-a288-23308a628d04/scratchpad
cp data/derived/sica_core.db "$SCRATCH/check.db"
sed "s#^sica_core_db = .*#sica_core_db = \"$SCRATCH/check.db\"#" config.toml > "$SCRATCH/config.check.toml"
cat > "$SCRATCH/dbcompare.py" <<'EOF'
import sqlite3, sys

def counts(path):
    c = sqlite3.connect(path)
    names = [r[0] for r in c.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
    return {n: c.execute(f'select count(*) from "{n}"').fetchone()[0] for n in names}

a, b = counts(sys.argv[1]), counts(sys.argv[2])
bad = 0
for n in sorted(set(a) | set(b)):
    diff = a.get(n) != b.get(n)
    bad += diff
    print(f"{n:34} {str(a.get(n, '-')):>10} {str(b.get(n, '-')):>10}{'   <-- DIFF' if diff else ''}")
sys.exit(1 if bad else 0)
EOF
uv run python -m sica_core.ingest --config "$SCRATCH/config.check.toml"
uv run python "$SCRATCH/dbcompare.py" data/derived/sica_core.db "$SCRATCH/check.db"
```
Expected: the ingest completes, and the compare shows identical counts in every table except `ingest_runs` (it gains rows, which is expected). Any other DIFF means a path was repointed wrongly.

- [ ] **Step 11: Commit (ask the user first)**

Proposed commands, to run only after the user approves:

```bash
git rm -r --cached data
git add .gitignore config.toml src/sica_core/paths.py src/sica_core/config.py \
        scripts/fetch_coops.py tests/test_data_layout.py \
        docs/superpowers/specs docs/superpowers/plans
git commit -m "Restructure data/ into raw/curated/derived and untrack it"
```
`git rm --cached` only stops tracking from now on; the old blobs stay in history.

---

### Task 3: Bring over `vhd`'s manual inputs and curated files

**Files:** copies only, into `data/raw/cov_foi/`, `data/raw/vanmaps/` and `data/curated/`.

**Interfaces:**
- Consumes: `DataPaths` from Task 2 (`foi_2023_extract`, `foi_2024_extract`, `vanmaps_addresses`, `landlord_mapping`, `chinatown_boundary`).
- Produces: the inputs Tasks 5 and 7 read.

- [ ] **Step 1: Copy the files (copy, not move: the originals stay as the archive until Task 10)**

```bash
V=~/Projects/VTU/vancouver-housing-data-dir
H=~/Projects/VTU/vancouver-housing-data
cp "$V/external/FOIs/FOI_2023_186/FOI_2023-186-release_rental_market.pdf" data/raw/cov_foi/
cp "$V/interim/all_rentals.2023-186.csv" data/raw/cov_foi/
cp "$V/external/FOIs/FOI_2024_698/2024-698-release.pdf" \
   "$V/external/FOIs/FOI_2024_698/2024-698_extracted_data.csv" data/raw/cov_foi/
cp "$V/raw/addresses.geojson" data/raw/vanmaps/addresses.geojson
cp "$H/landlord_mapping.toml" data/curated/landlord_mapping.toml
cp "$V/external/chinatown/expanded_ct_borders.geojson" data/curated/chinatown_boundary.geojson
```

- [ ] **Step 2: Verify the copies are byte-identical**

```bash
md5sum "$V/interim/all_rentals.2023-186.csv" data/raw/cov_foi/all_rentals.2023-186.csv \
       "$V/raw/addresses.geojson" data/raw/vanmaps/addresses.geojson \
       "$H/landlord_mapping.toml" data/curated/landlord_mapping.toml \
       "$V/external/chinatown/expanded_ct_borders.geojson" data/curated/chinatown_boundary.geojson
```
Expected: each pair of md5 lines matches.

- [ ] **Step 3: Confirm the 2023 extract is the untouched pre-merge file**

```bash
head -c 300 data/raw/cov_foi/all_rentals.2023-186.csv
```
Expected: header `id,Address,Local_Area,Current rental units,Year built,Current zoning` (no `foi_release` column). If `foi_release` is present, the file was written after a merge; stop and ask the user, because Task 5 needs the original.

No commit: nothing here is tracked.

---

### Task 4: Shared address helpers, GeoJSON loader and dependencies

**Files:**
- Create: `src/sica_core/prepare/__init__.py`, `src/sica_core/prepare/address.py`, `src/sica_core/prepare/io.py`
- Create: `tests/test_prepare_address.py`
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`)

**Interfaces:**
- Produces: `sica_core.prepare.address.clean_address(address: str | None) -> str | None`, `fix_street_names(street_name: str | None) -> str | None`, and `sica_core.prepare.io.load_polars(file: Path) -> polars.DataFrame`. Tasks 5 and 7 import these names.

- [ ] **Step 1: Add the dependencies**

```bash
uv add polars geopandas pyogrio tomlkit requests
uv run python -c "import polars, geopandas, tomlkit, requests; print(polars.__version__)"
```
Expected: a polars version at or above 1.0 (the ported scripts were written against 1.x; `vhd`'s venv had 1.43).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_prepare_address.py`:

```python
from sica_core.prepare.address import clean_address, fix_street_names


def test_clean_address_abbreviates_and_strips():
    assert clean_address("1234 Burrard Street") == "1234 burrard st"
    assert clean_address("10 W. 5th Ave") == "10 w 5th av"
    assert clean_address("5 Main Way") == "5 main w"
    assert clean_address("77 Pine Road") == "77 pine rd"


def test_clean_address_passes_none_through():
    assert clean_address(None) is None


def test_fix_street_names_moves_trailing_direction_to_front():
    assert fix_street_names("Georgia W") == "w georgia"
    assert fix_street_names("Main St") == "Main St"
    assert fix_street_names(None) is None
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_prepare_address.py -v`
Expected: FAIL, `No module named 'sica_core.prepare'`.

- [ ] **Step 4: Implement**

Create `src/sica_core/prepare/__init__.py` containing only:

```python
"""Ported from the retired `vhd` pipeline (business logic unchanged)."""
```

Create `src/sica_core/prepare/address.py`. This is the single copy of the function that `vhd` had in three places; do not "fix" its behaviour (see the note below):

```python
"""Address cleaning used by the prepare steps (ported from vhd, unchanged)."""

from __future__ import annotations

import re

NON_ALPHA_NUM = r"[^a-z0-9 ]"
DIRECTIONS = ["e", "w", "n", "nw", "ne", "s", "sw", "se"]


def clean_address(address: str | None) -> str | None:
    if address is None:
        return None
    address = address.lower()
    address = re.sub(NON_ALPHA_NUM, "", address)
    address = (
        address.replace(" street", " st")
        .replace(" avenue", " av")
        .replace(" drive", " dr")
        .replace(" road", " rd")
        .replace(" way", " w")
        .replace(" drive", " dr")
    )
    address = address.replace(" str", " st").replace(" ave", " av")
    return address


def fix_street_names(street_name: str | None) -> str | None:
    if street_name is None:
        return None
    parts = street_name.lower().split(" ")
    if parts and parts[-1] in DIRECTIONS:
        return " ".join(parts[-1:] + parts[:-1])
    return street_name
```

Create `src/sica_core/prepare/io.py`:

```python
"""GeoJSON -> polars loader shared by the prepare steps (ported from vhd)."""

from __future__ import annotations

from pathlib import Path

import polars as pl


def load_polars(file: Path) -> pl.DataFrame:
    return (
        pl.read_json(file)
        .select("features")
        .explode("features")
        .unnest("features")
        .select("properties")
        .unnest("properties")
    )
```

**Known quirk, deliberately preserved:** `.replace(" str", " st")` also rewrites the start of any word beginning with " str" (e.g. `1 strathcona ave` becomes `1 stathcona av`). Both sides of every join go through the same function, so matching still works, and changing it would change `buildings.csv`. Record it in the spec's deferred list; do not fix it here.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_prepare_address.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit (ask the user first)**

```bash
git add pyproject.toml uv.lock src/sica_core/prepare tests/test_prepare_address.py
git commit -m "Add shared address helpers and GeoJSON loader for the prepare steps"
```

---

### Task 5: FOI merge

**Files:**
- Create: `src/sica_core/prepare/foi.py`
- Create: `tests/test_prepare_foi.py`

**Interfaces:**
- Consumes: `clean_address` from Task 4.
- Produces: `sica_core.prepare.foi.merge_foi_releases(extract_2023: Path, extract_2024: Path, out: Path) -> int` (returns the merged row count). Task 7's CLI calls it with `DataPaths.foi_2023_extract`, `foi_2024_extract`, `all_rentals`.

This differs from `vhd`'s `merge_foi_releases.py` in one deliberate way: `vhd` read `interim/all_rentals.csv` as the 2023 input *and* overwrote it with the result, so a second run treated the merged file as 2023 data. Here the 2023 input is the raw `all_rentals.2023-186.csv` and the output is a separate derived file, so the step is idempotent. The redundant backup write is dropped for the same reason.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prepare_foi.py`:

```python
import polars as pl

from sica_core.prepare.foi import merge_foi_releases


def _write_inputs(tmp_path):
    f2023 = tmp_path / "2023.csv"
    f2023.write_text(
        "id,Address,Local_Area,Current rental units,Year built,Current zoning\n"
        "0,100 Main Street,Downtown Eastside,10,1950,RM-4\n"
        "1,200 Oak Street,Kitsilano,5,1960,RM-4\n"
    )
    f2024 = tmp_path / "2024.csv"
    f2024.write_text(
        "Address,Total Rental Units,Year Built,Name,Currentuse\n"
        "100 Main St,12,1951,Main House,Apartment\n"
    )
    return f2023, f2024


def test_2024_wins_on_overlap_and_2023_fills_gaps(tmp_path):
    f2023, f2024 = _write_inputs(tmp_path)
    out = tmp_path / "interim" / "all_rentals.csv"

    n = merge_foi_releases(f2023, f2024, out)

    df = pl.read_csv(out)
    assert n == df.height == 2
    main = df.filter(pl.col("Address").str.contains("Main")).row(0, named=True)
    assert main["foi_release"] == "2024-698"
    assert main["Current rental units"] == 12
    oak = df.filter(pl.col("Address").str.contains("Oak")).row(0, named=True)
    assert oak["foi_release"] == "2023-186"


def test_is_idempotent(tmp_path):
    f2023, f2024 = _write_inputs(tmp_path)
    out = tmp_path / "all_rentals.csv"
    merge_foi_releases(f2023, f2024, out)
    first = pl.read_csv(out).sort("Address")
    merge_foi_releases(f2023, f2024, out)
    assert pl.read_csv(out).sort("Address").equals(first)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_prepare_foi.py -v`
Expected: FAIL, `No module named 'sica_core.prepare.foi'`.

- [ ] **Step 3: Implement**

Create `src/sica_core/prepare/foi.py`:

```python
"""Merge the 2023 (FOI 2023-186) and 2024 (FOI 2024-698) rental-market FOI
releases into one table, preferring the 2024 release wherever an address
appears in both (2024 has narrower coverage: 2,682 addresses vs 2023's
4,801, ~2,508 overlapping) and falling back to 2023 for the rest.

Ported from vhd's scripts/merge_foi_releases.py. Unlike the original, the
2023 input is the raw extract and the output is a separate file (the
original overwrote its own input, so a second run was not idempotent).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .address import clean_address

COMBINED_COLS = [
    "_norm_address",
    "Address",
    "Local_Area",
    "Current rental units",
    "Year built",
    "Current zoning",
    "Name",
    "Currentuse",
    "foi_release",
]


def merge_foi_releases(extract_2023: Path, extract_2024: Path, out: Path) -> int:
    # --- 2023 release (already in the pipeline schema) ---
    old = pl.read_csv(extract_2023).with_columns(
        _norm_address=pl.col("Address").map_elements(clean_address, return_dtype=pl.Utf8),
        foi_release=pl.lit("2023-186"),
    ).drop("id")

    # --- 2024 release (different schema: no Local_Area/Current zoning,
    # adds Name/Currentuse) ---
    new = pl.read_csv(extract_2024).rename(
        {
            "Address": "Address",
            "Total Rental Units": "Current rental units",
            "Year Built": "Year built",
        }
    ).with_columns(
        _norm_address=pl.col("Address").map_elements(clean_address, return_dtype=pl.Utf8),
        foi_release=pl.lit("2024-698"),
        **{
            "Local_Area": pl.lit(None, dtype=pl.Utf8),
            "Current zoning": pl.lit(None, dtype=pl.Utf8),
        },
    )

    # --- Merge: 2024 first so it wins the address-based de-dup ---
    old_aligned = old.with_columns(
        Name=pl.lit(None, dtype=pl.Utf8), Currentuse=pl.lit(None, dtype=pl.Utf8)
    ).select(COMBINED_COLS)
    new_aligned = new.select(COMBINED_COLS)

    merged = pl.concat([new_aligned, old_aligned]).unique(
        subset="_norm_address", keep="first"
    )
    n_2024 = merged.filter(pl.col("foi_release") == "2024-698").height
    n_2023 = merged.filter(pl.col("foi_release") == "2023-186").height
    print(
        f"Merged FOI releases: {merged.height} total addresses "
        f"({n_2024} from 2024-698, {n_2023} carried over from 2023-186 only)"
    )

    merged = merged.drop("_norm_address").with_row_index(name="id")
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.write_csv(out)
    return merged.height
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_prepare_foi.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit (ask the user first)**

```bash
git add src/sica_core/prepare/foi.py tests/test_prepare_foi.py
git commit -m "Port the FOI 2023/2024 merge into sica_core.prepare"
```

---

### Task 6: Open Data fetcher

**Files:**
- Create: `src/sica_core/fetch/__init__.py`, `src/sica_core/fetch/cov_open_data.py`
- Create: `scripts/fetch_cov_open_data.py`
- Create: `tests/test_fetch_cov_open_data.py`

**Interfaces:**
- Consumes: `DataPaths.cov_open_data` (Task 2).
- Produces: `sica_core.fetch.cov_open_data` with `Dataset`, `Download`, `DATASETS`, `DEFAULT_TAX_REPORT_YEAR`, `plan_downloads(out_dir, tax_report_year=DEFAULT_TAX_REPORT_YEAR, only=None) -> list[Download]`, `download(dl, get=requests.get, chunk_size=1 << 20) -> int` (bytes written) and `fetch_all(out_dir, tax_report_year=DEFAULT_TAX_REPORT_YEAR, only=None, get=requests.get, log=print) -> list[Download]`. File names are `<dataset-id>.<format>`, exactly what `DataPaths.cov()` expects.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fetch_cov_open_data.py`:

```python
import pytest
import requests

from sica_core.fetch.cov_open_data import download, fetch_all, plan_downloads


class FakeResponse:
    def __init__(self, chunks=(b"a;b\n", b"1;2\n"), fail_at=None, ok=True):
        self.chunks, self.fail_at, self.ok = chunks, fail_at, ok

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError("500")

    def iter_content(self, size):
        for i, chunk in enumerate(self.chunks):
            if i == self.fail_at:
                raise ConnectionError("dropped")
            yield chunk


def test_plan_covers_every_consumer_format(tmp_path):
    names = {d.out_path.name for d in plan_downloads(tmp_path)}
    assert names == {
        "local-area-boundary.csv", "local-area-boundary.geojson",
        "property-addresses.csv", "property-addresses.geojson",
        "property-tax-report.geojson",
        "business-licences.geojson",
        "non-market-housing.geojson",
        "rental-standards-current-issues.geojson",
        "block-outlines.csv",
        "block-numbers.csv",
    }


def test_only_the_tax_report_is_refined(tmp_path):
    plan = {d.dataset: d for d in plan_downloads(tmp_path, tax_report_year=2027)}
    assert plan["property-tax-report"].refine == "report_year:2027"
    assert all(d.refine is None for n, d in plan.items() if n != "property-tax-report")


def test_url_shape(tmp_path):
    (dl,) = plan_downloads(tmp_path, only=["block-numbers"])
    assert dl.url == (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/"
        "block-numbers/exports/csv"
    )


def test_unknown_dataset_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="nope"):
        plan_downloads(tmp_path, only=["nope"])


def test_download_writes_file_and_passes_refine(tmp_path):
    (dl,) = plan_downloads(tmp_path, only=["property-tax-report"])
    seen = {}

    def get(url, **kwargs):
        seen.update(kwargs)
        return FakeResponse()

    assert download(dl, get=get) == 8
    assert dl.out_path.read_bytes() == b"a;b\n1;2\n"
    assert seen["params"] == {"refine": "report_year:2026"}


def test_failed_download_keeps_the_existing_file(tmp_path):
    (dl,) = plan_downloads(tmp_path, only=["block-numbers"])
    dl.out_path.write_bytes(b"old data")

    with pytest.raises(ConnectionError):
        download(dl, get=lambda url, **kw: FakeResponse(fail_at=1))

    assert dl.out_path.read_bytes() == b"old data"
    assert not list(tmp_path.glob("*.part"))


def test_fetch_all_logs_each_file(tmp_path):
    lines = []
    done = fetch_all(
        tmp_path, only=["block-numbers"], get=lambda url, **kw: FakeResponse(), log=lines.append
    )
    assert [d.out_path.name for d in done] == ["block-numbers.csv"]
    assert any("block-numbers.csv" in line for line in lines)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_fetch_cov_open_data.py -v`
Expected: FAIL, `No module named 'sica_core.fetch'`.

- [ ] **Step 3: Implement**

Create `src/sica_core/fetch/__init__.py` containing only `"""Scripted acquisition of external sources."""`.

Create `src/sica_core/fetch/cov_open_data.py`:

```python
"""Download the Vancouver Open Data exports sica_core needs.

Replaces `scripts/sync_from_vhd.py` and vhd's download_data.py. Each dataset
is fetched in the formats its consumers read: CSV for the ingest
(raw_addresses, blocks, block numbers, local-area boundary) and GeoJSON for
the prepare steps (properties/buildings). Files land as
`<dataset-id>.<format>` so `DataPaths.cov()` can find them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import requests

BASE_URL = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
DEFAULT_TAX_REPORT_YEAR = 2026


@dataclass(frozen=True)
class Dataset:
    id: str
    formats: tuple[str, ...]
    refine: str | None = None  # may contain "{year}"


DATASETS = (
    Dataset("local-area-boundary", ("csv", "geojson")),
    Dataset("property-addresses", ("csv", "geojson")),
    Dataset("property-tax-report", ("geojson",), refine="report_year:{year}"),
    Dataset("business-licences", ("geojson",)),
    Dataset("non-market-housing", ("geojson",)),
    Dataset("rental-standards-current-issues", ("geojson",)),
    Dataset("block-outlines", ("csv",)),
    Dataset("block-numbers", ("csv",)),
)


@dataclass(frozen=True)
class Download:
    dataset: str
    fmt: str
    refine: str | None
    url: str
    out_path: Path


def plan_downloads(
    out_dir: str | Path,
    tax_report_year: int = DEFAULT_TAX_REPORT_YEAR,
    only: Sequence[str] | None = None,
) -> list[Download]:
    known = {d.id for d in DATASETS}
    unknown = sorted(set(only or ()) - known)
    if unknown:
        raise ValueError(f"unknown dataset(s): {', '.join(unknown)}")
    out_dir = Path(out_dir)
    plan: list[Download] = []
    for ds in DATASETS:
        if only and ds.id not in only:
            continue
        refine = ds.refine.format(year=tax_report_year) if ds.refine else None
        for fmt in ds.formats:
            plan.append(
                Download(
                    ds.id, fmt, refine,
                    f"{BASE_URL}/{ds.id}/exports/{fmt}",
                    out_dir / f"{ds.id}.{fmt}",
                )
            )
    return plan


def download(dl: Download, get: Callable = requests.get, chunk_size: int = 1 << 20) -> int:
    """Stream one export to disk. Writes to a .part file and renames on
    success, so a dropped connection never clobbers an existing good file."""
    dl.out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dl.out_path.with_name(dl.out_path.name + ".part")
    params = {"refine": dl.refine} if dl.refine else None
    total = 0
    try:
        r = get(dl.url, stream=True, params=params, timeout=120)
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size):
                f.write(chunk)
                total += len(chunk)
        os.replace(tmp, dl.out_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return total


def fetch_all(
    out_dir: str | Path,
    tax_report_year: int = DEFAULT_TAX_REPORT_YEAR,
    only: Sequence[str] | None = None,
    get: Callable = requests.get,
    log: Callable[[str], None] = print,
) -> list[Download]:
    plan = plan_downloads(out_dir, tax_report_year, only)
    for dl in plan:
        log(f"fetching {dl.out_path.name} ...")
        size = download(dl, get=get)
        log(f"  {dl.out_path.name}: {size / 1e6:.1f} MB")
    return plan
```

Create `scripts/fetch_cov_open_data.py`:

```python
#!/usr/bin/env python3
"""Fetch the Vancouver Open Data files into data/raw/cov_open_data/.

Usage:
    uv run python scripts/fetch_cov_open_data.py
    uv run python scripts/fetch_cov_open_data.py --only block-numbers block-outlines
    uv run python scripts/fetch_cov_open_data.py --tax-report-year 2027

The property tax report is large (~200 MB as GeoJSON) and business licences
~140 MB; a full fetch takes several minutes. Afterwards, update the fetch
dates in data/raw/cov_open_data/MANIFEST.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sica_core.fetch.cov_open_data import DEFAULT_TAX_REPORT_YEAR, fetch_all  # noqa: E402
from sica_core.paths import DataPaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument("--only", nargs="+", help="dataset ids to fetch (default: all)")
    parser.add_argument("--tax-report-year", type=int, default=DEFAULT_TAX_REPORT_YEAR)
    args = parser.parse_args()

    paths = DataPaths(args.data_dir)
    fetch_all(paths.cov_open_data, args.tax_report_year, args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_fetch_cov_open_data.py -v`
Expected: 7 PASS. Do not run the real fetch yet; that happens in Task 8, after the port is validated.

- [ ] **Step 5: Commit (ask the user first)**

```bash
git add src/sica_core/fetch scripts/fetch_cov_open_data.py tests/test_fetch_cov_open_data.py
git commit -m "Add Open Data fetcher for the 8 datasets sica_core uses"
```

---

### Task 7: Port `build_properties` and `build_buildings`, validate by replay

**Files:**
- Create: `src/sica_core/prepare/properties.py`, `src/sica_core/prepare/buildings.py`
- Create: `scripts/prepare_data.py`

**Interfaces:**
- Consumes: `DataPaths`, `clean_address`, `fix_street_names`, `load_polars`, `merge_foi_releases` (Tasks 2, 4, 5).
- Produces: `sica_core.prepare.properties.run(paths: DataPaths) -> None` (writes `paths.properties`), `sica_core.prepare.buildings.run(paths: DataPaths) -> None` (writes `paths.buildings` and `paths.ct_properties`), and the CLI `scripts/prepare_data.py [--data-dir D] [--stage foi|properties|buildings|all]`.

The scripts total ~590 lines, so this task ports them mechanically rather than retyping them: the bodies are copied from `vhd` and indented into a `run(paths)` function, and the few hand edits are given exactly below. The replay in Steps 6–8 is what proves the port is faithful. Test-driven development doesn't apply to the port itself; the comparison against `vhd`'s own output is the test.

- [ ] **Step 1: Create `properties.py`**

Write the header (everything above the body) with an editor, then append the indented body with the shell command that follows:

```python
"""Rebuild derived/interim/properties.csv from the raw Open Data files.

Ported from vhd's scripts/build_properties.py (logic unchanged). Includes the
VanMaps primary/secondary address resolution (raw/vanmaps/addresses.geojson)
and the Chinatown boundary flag (curated/chinatown_boundary.geojson).

Note on the Chinatown boundary: only one boundary file survives, an
"expanded" one. The original notebooks distinguished a narrower
`boundaries.shp` from a wider `ct_ext.shp`, so `chinatown=True` here may
cover more addresses than the original ~161-row baseline did.

Differences from the vhd script: paths come from DataPaths, clean_address and
fix_street_names are imported, and the one-off `properties.pre-refresh.csv`
backup is gone (derived files are regenerable).
"""

from __future__ import annotations

import geopandas
import polars as pl

from ..paths import DataPaths
from .address import clean_address, fix_street_names
from .io import load_polars


def run(paths: DataPaths) -> None:
    addresses_f = paths.vanmaps_addresses
    property_addresses_f = paths.cov("property-addresses", "geojson")
    property_tax_f = paths.cov("property-tax-report", "geojson")
    chinatown_boundary_f = paths.chinatown_boundary
    properties_f = paths.properties
    properties_f.parent.mkdir(parents=True, exist_ok=True)

```

Append the body, i.e. everything in vhd's script from the `# --- addresses.geojson` comment to the end of the file, indented one level (blank lines stay blank):

```bash
S=~/Projects/VTU/vancouver-housing-data/scripts
START=$(grep -n '^# --- addresses.geojson' "$S/build_properties.py" | cut -d: -f1)
tail -n +"$START" "$S/build_properties.py" | sed 's/^\(.\)/    \1/' >> src/sica_core/prepare/properties.py
uv run python -c "import sica_core.prepare.properties"
```
Expected: the import succeeds. (The body has no multi-line string literals, so indenting cannot change any string's content.)

- [ ] **Step 2: Create `buildings.py`**

Header:

```python
"""Rebuild derived/buildings.csv (one row per building, with landlord
attribution) and derived/ct_properties.csv from refreshed inputs.

Ported from vhd's scripts/build_buildings.py (logic unchanged: address
cleaning, the FOI/non-market/issues joins, the `Long-term Rental` business
licence filter, `bsns_group` from curated/landlord_mapping.toml, and the
`secondary_addresses` column). Removed: the writes of rental_properties.csv,
nm_rental_properties.csv, address_index.csv and landlord_summary.csv, which
nothing in this repo reads. vhd's own docstring records why the notebook
logic was reconstructed the way it was (the undefined `addresses` variable,
the retired Google Sheets push); that history stays in the archive.
"""

from __future__ import annotations

import polars as pl
import polars.selectors as cs
from tomlkit import parse

from ..paths import DataPaths
from .address import clean_address
from .io import load_polars

BC_versions = {
    "B C": "BC",
    "B.C.": "BC",
}


def run(paths: DataPaths) -> None:
    properties_f = paths.properties
    all_rentals_f = paths.all_rentals
    business_licenses_f = paths.cov("business-licences", "geojson")
    non_market_housing_f = paths.cov("non-market-housing", "geojson")
    rental_standards_issues_f = paths.cov("rental-standards-current-issues", "geojson")
    landlord_mapping_f = paths.landlord_mapping
    buildings_f = paths.buildings
    ct_properties_f = paths.ct_properties
    buildings_f.parent.mkdir(parents=True, exist_ok=True)

    CLEAN = lambda col: pl.col(col).map_elements(clean_address, return_dtype=pl.Utf8)

    pl.Config.set_tbl_rows(10)

```

Generate the body with the deletions applied first. This script asserts each deletion matched exactly once, so a mismatch fails loudly instead of silently keeping dead code:

```bash
cat > "$SCRATCH/port_buildings.py" <<'EOF'
import re, sys
src = open(sys.argv[1]).read()
src = src[src.index("# --- Datasets ---"):]
cuts = [
    r"^rental_properties = \(.*?^print\(f\"rental_properties\.csv[^\n]*\n",
    r"^nm_rental_props = \(.*?^print\(f\"nm_rental_properties\.csv[^\n]*\n",
    r"^address_index = \(.*?^print\(f\"address_index\.csv[^\n]*\n",
    r"^# --- Bonus:.*\Z",
]
for pat in cuts:
    src, n = re.subn(pat, "", src, count=1, flags=re.S | re.M)
    assert n == 1, f"no match for {pat}"
sys.stdout.write("".join(("    " + l if l.strip() else l) for l in src.splitlines(keepends=True)))
EOF
uv run python "$SCRATCH/port_buildings.py" ~/Projects/VTU/vancouver-housing-data/scripts/build_buildings.py \
  >> src/sica_core/prepare/buildings.py
uv run python -c "import sica_core.prepare.buildings"
```
Expected: the import succeeds. Then:

- `grep -nE "rental_properties|nm_rental|address_index|landlord_summary|_f\b" src/sica_core/prepare/buildings.py` should show only the path variables defined in the header, plus `properties_f`, `all_rentals_f`, etc. being *used*; no reference to a deleted variable. If Python raises `NameError` at replay time for a deleted name, delete the remaining reference.

- [ ] **Step 3: Create the CLI**

Create `scripts/prepare_data.py`:

```python
#!/usr/bin/env python3
"""Build the derived tables from raw/ and curated/.

Stages, in dependency order:
  foi         raw/cov_foi 2023 + 2024 extracts  -> derived/interim/all_rentals.csv
  properties  raw/cov_open_data + raw/vanmaps   -> derived/interim/properties.csv
  buildings   the above + curated/              -> derived/buildings.csv, ct_properties.csv

Usage: uv run python scripts/prepare_data.py [--data-dir data] [--stage all]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sica_core.paths import DataPaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument(
        "--stage", choices=["foi", "properties", "buildings", "all"], default="all"
    )
    args = parser.parse_args()
    paths = DataPaths(args.data_dir)
    stage = args.stage

    if stage in ("foi", "all"):
        from sica_core.prepare.foi import merge_foi_releases

        merge_foi_releases(paths.foi_2023_extract, paths.foi_2024_extract, paths.all_rentals)
    if stage in ("properties", "all"):
        from sica_core.prepare import properties

        properties.run(paths)
    if stage in ("buildings", "all"):
        from sica_core.prepare import buildings

        buildings.run(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write the comparison tool (scratch, not committed)**

```bash
cat > "$SCRATCH/compare_csv.py" <<'EOF'
"""compare_csv.py NEW OLD [KEY|-] [DROP_COLS]

With KEY: per-column mismatch counts over rows present in both files.
Without: multiset comparison of whole rows. ';'-joined lists are compared
order-insensitively (polars .unique() emits them in arbitrary order)."""
import sys
from collections import Counter
import pandas as pd

new_p, old_p = sys.argv[1:3]
key = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
drop = sys.argv[4].split(",") if len(sys.argv) > 4 else []

def load(p):
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    return df.drop(columns=[c for c in drop if c in df.columns])

canon = lambda v: ";".join(sorted(v.split(";")))
new, old = load(new_p), load(old_p)
print("columns only in old:", sorted(set(old.columns) - set(new.columns)))
print("columns only in new:", sorted(set(new.columns) - set(old.columns)))
cols = [c for c in old.columns if c in new.columns]
new = new[cols].apply(lambda s: s.map(canon))
old = old[cols].apply(lambda s: s.map(canon))
print("rows: new", len(new), " old", len(old))
if key:
    n, o = new.set_index(key), old.set_index(key)
    assert n.index.is_unique and o.index.is_unique, f"{key} is not unique"
    print("keys only in new:", len(n.index.difference(o.index)),
          " only in old:", len(o.index.difference(n.index)))
    both = n.index.intersection(o.index)
    for c in n.columns:
        m = int((n.loc[both, c] != o.loc[both, c]).sum())
        if m:
            print(f"  column {c}: {m} of {len(both)} rows differ")
else:
    cn = Counter(map(tuple, new.itertuples(index=False)))
    co = Counter(map(tuple, old.itertuples(index=False)))
    print("rows only in new:", sum((cn - co).values()),
          " only in old:", sum((co - cn).values()))
EOF
```

- [ ] **Step 5: Stage a replay directory that mirrors `vhd`'s inputs**

Symlinks avoid copying ~500 MB of GeoJSON:

```bash
R="$SCRATCH/replay"; rm -rf "$R"
V=~/Projects/VTU/vancouver-housing-data-dir
mkdir -p "$R/raw/cov_open_data" "$R/raw/cov_foi" "$R/raw/vanmaps" "$R/curated"
for d in property-addresses property-tax-report business-licences non-market-housing rental-standards-current-issues; do
  ln -s "$V/raw/$d.geojson" "$R/raw/cov_open_data/$d.geojson"
done
ln -s "$V/raw/addresses.geojson" "$R/raw/vanmaps/addresses.geojson"
cp data/raw/cov_foi/all_rentals.2023-186.csv data/raw/cov_foi/2024-698_extracted_data.csv "$R/raw/cov_foi/"
cp data/curated/landlord_mapping.toml data/curated/chinatown_boundary.geojson "$R/curated/"
uv run python scripts/prepare_data.py --data-dir "$R"
```
Expected: the three stages run and print row counts (the FOI merge prints roughly `4,8xx total addresses`; the buildings step prints its `businesses`, `housing` and `buildings.csv` counts) with no traceback.

- [ ] **Step 6: Compare against `vhd`'s own outputs**

```bash
V=~/Projects/VTU/vancouver-housing-data-dir
uv run python "$SCRATCH/compare_csv.py" "$R/derived/interim/all_rentals.csv" "$V/interim/all_rentals.csv" - id
uv run python "$SCRATCH/compare_csv.py" "$R/derived/interim/properties.csv" "$V/interim/properties.csv"
uv run python "$SCRATCH/compare_csv.py" "$R/derived/buildings.csv" "$V/processed/buildings.csv" address
uv run python "$SCRATCH/compare_csv.py" "$R/derived/ct_properties.csv" "$V/processed/ct_properties.csv" address
```
Expected:
- `all_rentals` (id column dropped): `rows only in new: 0  only in old: 0`.
- `properties`: 0 and 0, or a handful of rows.
- `buildings` and `ct_properties`: `keys only in new: 0  only in old: 0`, no `columns only in` lines, and per-column mismatch counts of zero or small. `vhd` collapses each address with `.unique()` followed by `.list.first()`, which picks an arbitrary element when an address has several distinct values, so a few rows can legitimately differ run to run. Step 7 measures how much.

- [ ] **Step 7: Measure the run-to-run noise floor**

```bash
R2="$SCRATCH/replay2"; rm -rf "$R2"; cp -a "$R" "$R2"; rm -rf "$R2/derived"
uv run python scripts/prepare_data.py --data-dir "$R2"
uv run python "$SCRATCH/compare_csv.py" "$R2/derived/buildings.csv" "$R/derived/buildings.csv" address
```
Expected: mismatch counts in the same columns and of the same size as Step 6's `buildings` counts. If the counts against `vhd` are within that noise, the port is faithful. If a column differs against `vhd` but *not* between the two runs, or `keys only in new/old` is non-zero, the port changed behaviour: diff the offending step against the `vhd` script and fix the port before going on.

- [ ] **Step 8: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass (10 from Task 2, plus 3 + 2 + 7 added since = 22).

- [ ] **Step 9: Commit (ask the user first)**

```bash
git add src/sica_core/prepare/properties.py src/sica_core/prepare/buildings.py scripts/prepare_data.py
git commit -m "Port vhd's properties and buildings builds into sica_core.prepare"
```

---

### Task 8: First real refresh: fetch, prepare, ingest, validate, render

**Files:** none created or edited. This task runs the pipeline end to end on fresh data. Only ignored files change, so there is nothing to commit.

**Interfaces:**
- Consumes: everything from Tasks 2–7.
- Produces: fresh `data/raw/cov_open_data/*`, `data/derived/*`, an updated `data/derived/sica_core.db`, and `www/index.html`.

This is the first time the 2024 address CSVs are replaced with current data, so expect some real differences. The goal is to look at each one, not to make them zero.

- [ ] **Step 1: Fetch (needs network; several minutes, ~500 MB)**

```bash
uv run python scripts/fetch_cov_open_data.py
ls -la --time-style=+%F data/raw/cov_open_data/
```
Expected: 10 files, all dated today, no `.part` files left. If one download fails, re-run with `--only <dataset-id>`; a failed fetch never overwrites an existing file.

- [ ] **Step 2: Check the new CSV headers against what the ingest allows**

The ingest raises on any column it has no mapping for, by design ("don't drop silently"). Check before running it:

```bash
for f in property-addresses local-area-boundary block-outlines block-numbers; do
  printf '%s: ' "$f"; head -1 "data/raw/cov_open_data/$f.csv" | tr -d '\357\273\277'
done
```
Expected: `property-addresses` shows `civic_number;geo_local_area;geom;p_parcel_id;pcoord;site_id;std_street;geo_point_2d` (order may differ); `block-outlines` shows `Geom;geo_point_2d`. If a header has a column the ingest doesn't know, the ingest will stop with a message naming it in Step 5. That is a schema change: stop and ask the user before editing `RAW_*_COLUMNS` and `schema.sql`.

- [ ] **Step 3: Prepare**

```bash
uv run python scripts/prepare_data.py
wc -l data/derived/buildings.csv data/derived/ct_properties.csv data/derived/interim/*.csv
```
Expected: no traceback; `buildings.csv` in the same ballpark as the previous pull (5,146 rows on 2026-08-07); a row count that differs by more than ~10% deserves a look at the printed step counts before continuing.

- [ ] **Step 4: Back up the database, then ingest into it**

The real db is used (not a copy) because `ownership_claims` and `ingest_runs` must persist across rebuilds; the backup is the way back.

```bash
cp data/derived/sica_core.db data/derived/sica_core.pre-refresh.db
uv run python -m sica_core.ingest --config config.toml
```
Expected: per-source row counts, no traceback. On failure, restore with `cp data/derived/sica_core.pre-refresh.db data/derived/sica_core.db` and diagnose.

- [ ] **Step 5: Validate the database against the backup**

```bash
uv run python "$SCRATCH/dbcompare.py" data/derived/sica_core.pre-refresh.db data/derived/sica_core.db
```
Expected:
- `ownership_claims` (and any claims-derived table): **identical**. If this differs, stop and restore the backup.
- `ingest_runs`: gains rows.
- `raw_addresses`, `raw_block_numbers`, `raw_buildings`, `buildings`, `addresses`, `blocks`: may differ; they now come from 2026 data. Read the numbers and confirm they are plausible (a table dropping to near zero is not).
- Membership tables: identical (no input changed).

- [ ] **Step 6: Regenerate the PID map and render the map**

```bash
uv run python scripts/export_pid_address_map.py
uv run python scripts/rebuild_map.py
```
Expected: both complete; `www/index.html` is rewritten. Open it and check that markers appear across the city, the sidebar table populates, and landlord clusters still show. Compare the marker count with what the previous build showed.

- [ ] **Step 7: Decide, then clean up**

If everything looks right, keep `sica_core.pre-refresh.db` until the user has looked at the map, then delete it. If not, restore it (Step 4) and report what differed.

---

### Task 9: Manifests, docs and stale-path cleanup

**Files:**
- Create: `data/README.md`, `data/raw/{cov_open_data,cov_foi,vanmaps,chf_bc,nationbuilder,samwise}/MANIFEST.md`
- Modify: `docs/DATA_SOURCES.md`, `CLAUDE.md`, and the docstrings under `src/` and `scripts/` that name old paths

**Interfaces:**
- Consumes: the final layout and the fetch dates from Task 8.

- [ ] **Step 1: Write `data/README.md`**

```markdown
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
uv run python -m sica_core.ingest --config config.toml          # derived/sica_core.db
uv run python scripts/export_pid_address_map.py                 # derived/pid_address_map.csv
uv run python scripts/rebuild_map.py                            # www/index.html
```

Sources without a fetch script (FOI, VanMaps, NationBuilder, Samwise) are
manual: see each folder's `MANIFEST.md` for what to put there.
```

- [ ] **Step 2: Generate the `cov_open_data` manifest**

```bash
{
cat <<'EOF'
# raw/cov_open_data — Vancouver Open Data

- **Source:** https://opendata.vancouver.ca (Explore API v2.1 exports)
- **Method:** scripted, `uv run python scripts/fetch_cov_open_data.py` (`--only <id>` for one dataset)
- **License:** Open Government Licence – Vancouver (confirm per dataset before publishing derived data)
- **Refresh:** ad hoc. `property-tax-report` is filtered to one `report_year` (`--tax-report-year`).

| File | Fetched | Size |
|---|---|---|
EOF
for f in data/raw/cov_open_data/*.csv data/raw/cov_open_data/*.geojson; do
  printf '| %s | %s | %s |\n' "$(basename "$f")" "$(date -r "$f" +%F)" "$(du -h "$f" | cut -f1)"
done
} > data/raw/cov_open_data/MANIFEST.md
cat data/raw/cov_open_data/MANIFEST.md
```

- [ ] **Step 3: Write the other five manifests**

Each states only what is known. Where something genuinely was not recorded, it says so.

`data/raw/cov_foi/MANIFEST.md`:

```markdown
# raw/cov_foi — City of Vancouver FOI releases

- **Method:** manual. The City releases a PDF; the table in it is extracted to CSV by hand.
- **Files:**
  - `FOI_2023-186-release_rental_market.pdf` (original, 2023-04-25) and `all_rentals.2023-186.csv` (extracted from it with `tabula`, pages 3–56; the extraction is not reproduced by this repo).
  - `2024-698-release.pdf` (original) and `2024-698_extracted_data.csv` (extracted by hand).
  - `sra_housing_combined.csv`, `rezoning_applications.csv`: **origin unverified** (see docs/DATA_SOURCES.md).
- **Used by:** `scripts/prepare_data.py --stage foi` (the two FOI extracts); `sica_core` ingest (`raw_sro`, `raw_rezoning`).
- **Do not hand-edit** the extracted CSVs; re-extract from the PDF instead.
```

`data/raw/vanmaps/MANIFEST.md`:

```markdown
# raw/vanmaps — VanMaps

- **Files:** `addresses.geojson`, exported from VanMaps 2024-03-11 (per the file date). Gives each civic address a primary/secondary flag, used to resolve secondary addresses to a building's primary address.
- **Method:** manual. The exact export steps were not recorded when the `vhd` pipeline was written. TODO: write them down the next time this is re-exported.
- **Used by:** `scripts/prepare_data.py --stage properties`.
```

`data/raw/chf_bc/MANIFEST.md`:

```markdown
# raw/chf_bc — CHF BC co-op housing list

- **Source:** the CHF BC website (a third party's own site, not the City or VTU).
- **Method:** scripted, `uv run python scripts/fetch_coops.py` (replayable from saved HTML with its `--html-file` option).
- **File:** `coops_vancouver.csv`.
- **Used by:** `sica_core` ingest (`raw_coops`) and the map's co-op overlay.
```

`data/raw/nationbuilder/MANIFEST.md`:

```markdown
# raw/nationbuilder — VTU membership (PRIVATE)

- **Files:** `membership_full.csv` (raw, un-anonymized, 154 columns), `vtu_members.csv` (likely orphaned).
- **Method:** manual export from NationBuilder, on VTU's own cadence.
- **Never commit or share.** The public-safe derivative is `derived/vtu_membership_public.csv`, built by `scripts/build_vtu_public_extract.py`.
```

`data/raw/samwise/MANIFEST.md`:

```markdown
# raw/samwise — BC Land Owner Transparency Registry export (PRIVATE)

- **File:** `samwise-export.csv`, produced by the separate `samwise` tool and dropped in by hand.
- **Method:** manual. Imported into claims with `scripts/import_lotr_claims.py`.
- **Do not share:** it holds ownership records from the registry.
```

- [ ] **Step 4: Confirm only the README and manifests are trackable**

```bash
git add -n data/
```
Expected: exactly seven lines, for `data/README.md` and the six `MANIFEST.md` files. Anything else means the ignore pattern leaks; stop and fix `.gitignore`.

- [ ] **Step 5: Update `docs/DATA_SOURCES.md`**

Make these edits by hand:

1. **Scope** bullet 2: change "parsing a `data/*.csv`" to "parsing a `data/raw/**` file".
2. **Conventions → "Retain originals"**: replace the bullet with: "**Retain originals.** Where a source arrives as a document (FOI PDF, a scraped page), the as-received file is kept in its `data/raw/<source>/` folder beside the extracted CSV. Nothing under `data/` is tracked by git; the record of what was fetched, when and how is that folder's `MANIFEST.md`."
3. **Summary table**: for `property_addresses.csv`, `block-outlines.csv`, `block-numbers.csv` and `local-area-boundary.csv` set "Refresh cadence" to "On demand (`fetch_cov_open_data.py`)". For `buildings.csv` set category to "Derived: built by `prepare_data.py` from Open Data + FOI" and cadence "Rebuilt after a fetch". Update "Last fetched" to the Task 8 date.
4. **`buildings.csv`, `property_addresses.csv`, `local-area-boundary.csv` entries**: replace each "Origin" and "Access method" paragraph that describes `vhd` with: "Fetched directly from Open Data by `scripts/fetch_cov_open_data.py` (buildings.csv is built from several of those files plus the FOI extracts by `scripts/prepare_data.py`). Until 2026-09 this came from a separate pipeline repo, `vhd`, since retired; its logic now lives in `src/sica_core/prepare/`." Keep every "Format/known quirks" bullet, they are still true.
5. Add one quirk bullet under `buildings.csv`: "`clean_address` (ported unchanged) rewrites any word starting with ` str` (e.g. `strathcona` becomes `stathcona`). Both sides of each join use the same function, so matching works; do not change it without rebuilding everything."
6. **Delete the "### Syncing from vhd" section** and replace it with:

```markdown
### Fetching Open Data

`scripts/fetch_cov_open_data.py` downloads the 8 Open Data datasets into
`data/raw/cov_open_data/` (CSV for the ingest, GeoJSON for the prepare steps).
Then `scripts/prepare_data.py` rebuilds `data/derived/`. See `data/README.md`
for the full rebuild order.
```

7. Replace every remaining "Output location" path with the new one, using the table in Task 2 Step 5.
8. Update the "Last updated" date at the top.

- [ ] **Step 6: Update stale paths in code and docstrings**

```bash
sed -i \
  -e 's#data/property_addresses\.csv#data/raw/cov_open_data/property-addresses.csv#g' \
  -e 's#data/block-numbers\.csv#data/raw/cov_open_data/block-numbers.csv#g' \
  -e 's#data/block-outlines\.csv#data/raw/cov_open_data/block-outlines.csv#g' \
  -e 's#data/buildings\.csv#data/derived/buildings.csv#g' \
  -e 's#data/sra_housing_combined\.csv#data/raw/cov_foi/sra_housing_combined.csv#g' \
  -e 's#data/rezoning_applications\.csv#data/raw/cov_foi/rezoning_applications.csv#g' \
  -e 's#data/coops_vancouver\.csv#data/raw/chf_bc/coops_vancouver.csv#g' \
  -e 's#data/Nationbuilder/#data/raw/nationbuilder/#g' \
  -e 's#data/Samwise/#data/raw/samwise/#g' \
  -e 's#data/vtu_membership_public\.csv#data/derived/vtu_membership_public.csv#g' \
  -e 's#data/sica_core\.db#data/derived/sica_core.db#g' \
  $(grep -rlE "data/(property_addresses|block-|buildings|sra_housing|rezoning|coops_vancouver|Nationbuilder|Samwise|vtu_membership|sica_core\.db)" src scripts --include='*.py' | grep -v sync_from_vhd)
grep -rnE "data/(property_addresses|buildings\.csv|Nationbuilder|Samwise|coops_vancouver|sra_housing|rezoning_applications|sica_core\.db|vtu_membership|block-)" src scripts tests README.md CLAUDE.md docs/DATA_SOURCES.md | grep -v "sync_from_vhd"
```
Expected: the final grep prints nothing. Anything it prints is a stale path (or a path that legitimately mentions the old name in history, such as "previously"); fix or reword it. Then `uv run pytest -q` must still pass.

- [ ] **Step 7: Add a pointer in `CLAUDE.md`**

In Section 3, directly under "Known data sources (Q4)" after the last bullet, add: "The on-disk layout (`raw/` → `curated/` → `derived/`) and rebuild order are described in [`data/README.md`](data/README.md); everything under `data/` except the README and per-source manifests is gitignored." Bump the "Last updated" date at the top.

- [ ] **Step 8: Commit (ask the user first)**

```bash
git add data/README.md data/raw/*/MANIFEST.md docs/DATA_SOURCES.md CLAUDE.md src scripts
git commit -m "Document the data layout with manifests and update stale paths"
```

---

### Task 10: Retire `vhd`

**Files:**
- Delete: `scripts/sync_from_vhd.py`
- Delete (outside the repo, only after explicit confirmation): `~/Projects/VTU/vancouver-housing-data`, `~/Projects/VTU/vancouver-housing-data-dir`

**Interfaces:**
- Consumes: the archive from Task 1, and a successful Task 8.

- [ ] **Step 1: Confirm nothing still depends on `vhd`**

```bash
grep -rn "sync_from_vhd\|VHD_DATA_DIR\|vancouver-housing-data" src scripts tests config.toml README.md CLAUDE.md docs/DATA_SOURCES.md
```
Expected: only `scripts/sync_from_vhd.py` itself, plus any deliberate history notes in `DATA_SOURCES.md` ("Until 2026-09 this came from ... `vhd`"). Anything else is a live dependency; fix it first.

- [ ] **Step 2: Delete the sync script**

```bash
rm scripts/sync_from_vhd.py
uv run pytest -q
```
Expected: all tests pass.

- [ ] **Step 3: Re-verify the archive still opens**

```bash
BK=~/Projects/VTU/_archive/2026-09-18-data-restructure
tar tzf "$BK/vancouver-housing-data.tgz" | wc -l
tar tzf "$BK/vancouver-housing-data-dir.tgz" | wc -l
```
Expected: both non-zero (about 30 and about 40 entries respectively).

- [ ] **Step 4: Ask the user before deleting the two directories**

Show them what will be removed and its size (`du -sh ~/Projects/VTU/vancouver-housing-data ~/Projects/VTU/vancouver-housing-data-dir`). Neither is under git, so the archive from Task 1 is the only copy after this. Delete only after an explicit yes:

```bash
rm -rf ~/Projects/VTU/vancouver-housing-data ~/Projects/VTU/vancouver-housing-data-dir
```

- [ ] **Step 5: Update the memory notes**

Edit `project_vhd_sync_workflow.md` and `project_vhd_repo_buildings_csv_origin.md` in the project memory to say `vhd` was retired on this date, that its logic is now `src/sica_core/prepare/` plus `scripts/fetch_cov_open_data.py` and `scripts/prepare_data.py`, and that the archive lives at `~/Projects/VTU/_archive/2026-09-18-data-restructure/`. Update the two matching lines in `MEMORY.md`.

- [ ] **Step 6: Commit (ask the user first)**

```bash
git add -A scripts
git commit -m "Retire sync_from_vhd.py now that the pipeline lives in this repo"
```

---

## Follow-ups found while planning (not part of this plan)

- `clean_address` mangles words starting with ` str` (Task 4 note). Fixing it changes every join key, so it needs its own change.
- `vhd`'s `.unique().list.first()` collapse is not deterministic when an address has several distinct values (Task 7, Step 7 measures it). Making it deterministic would change `buildings.csv` slightly.
- `DEFAULT_TAX_REPORT_YEAR = 2026` is a constant; it needs bumping each year, or deriving from the current date.
- The VanMaps export steps were never recorded (`raw/vanmaps/MANIFEST.md` says so).
- The origins of `sra_housing_combined.csv` and `rezoning_applications.csv` are still unverified.
- `exports/` is created but unwired; named export views are deferred in the spec.
