# Landlord Listings as a Building Source — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Landlord and manager portfolio listings add buildings the City doesn't list, set `managed_by` for known managers, and link each building to the company's own page.

**Architecture:**
- Listing snapshots already land in PERSISTENT `raw_manager_listings`. A new
  `usable_listings()` keeps only listings that are current and already built.
- The merge appends a building for each usable listing that matches no City-source
  building but does exactly match a City address point.
- `building_names.py` also writes a REBUILDABLE `building_listings` link table.
- The export turns those links into a `listings` column and a listing-based
  `managed_by`, and the popup renders them.

**Tech Stack:** Python 3 (`uv`, pytest, pandas, sqlite3), TypeScript (Vite, vitest), TOML curated config.

**Spec:** `docs/superpowers/specs/2026-09-30-landlord-listings-source-design.md`

## Global Constraints

- **No git actions.** Never run `git add`/`git commit`/any git write without asking the
  user first, and never add Claude attribution. The "Checkpoint" step at the end of each
  task is a stop to report, not a commit.
- **No staff contacts.** Staff contact details in snapshots must never reach the DB or the
  map. Only id, name, address, URL, status, units and dates are stored.
- **Gitignored data.** Raw snapshots under `data/raw/` and curated files under
  `data/curated/` are gitignored. Never add them to git.
- **Unbuilt statuses**, compared case-insensitively after trimming:
  `UNBUILT_STATUSES = ("in development", "coming soon")`.
- **Current listing:** `last_seen` equals the max `last_seen` of its manager.
- **Building source label:** `building_source = "manager listing"`, ranked last in
  `BUILDING_SOURCE_ORDER`.
- **Listings never supply an owner.** A listing-created building's owner is `(Unknown)`,
  with key `unknown`.
- **Only `property_managers.toml` managers set `managed_by`.** Owner-operators (Wall)
  never do.
- **New public export columns:** `managed_by_source` (`"licence"`, `"listing"` or null) and
  `listings` (a list of `{"by", "url", "seen"}`).
- **Popup wording:**
  - "Managed by <name>"
  - "Listed by <company> ↗"
  - "Company website, seen <YYYY-MM-DD>"
  - "Added from <company>'s listings"
- **Commands:** Python tests `uv run pytest`; frontend tests `cd frontend && npm test`;
  typecheck `cd frontend && npm run typecheck`.

## Review Focus

1. **A manager's newest snapshot is empty for Vancouver** (every listing outside the
   city). Its older listings must not stay "current". This holds because `max(last_seen)`
   is taken over stored rows only. Pinned in Task 1.
2. **Two companies list the same new address** (a manager and an owner). That must make
   one building with two `listings` entries, not two buildings. Pinned in Tasks 2 and 4.
3. **A listing URL that isn't http(s).** It must render as plain text, never as a link.
   Pinned in Task 6.
4. **A database built before this change.** The PERSISTENT listings table lacks
   `status`/`units`. `init_db` must add them without losing rows. Pinned in Task 1.
5. **A listing that matches a City building only by street-type typo** ("Ave" vs "St").
   It must attach to that building rather than create a twin. Pinned in Task 2.

---

### Task 1: Listing status, units and `usable_listings()`

**Files:**
- Modify: `src/tc_core/schema.sql` (the `raw_manager_listings` CREATE, ~line 434)
- Modify: `src/tc_core/db.py`
- Modify: `src/tc_core/ingest/manager_listings.py`
- Test: `tests/test_manager_listings.py`

**Interfaces:**
- Produces:
  - `tc_core.ingest.manager_listings.UNBUILT_STATUSES: tuple[str, ...]`
  - `tc_core.ingest.manager_listings.usable_listings(conn) -> list[dict]`. Each dict has
    the keys `listing_row_id, manager, name, address, url, last_seen, units`.
  - Columns `raw_manager_listings.status TEXT` and `raw_manager_listings.units INTEGER`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_manager_listings.py`, change `_listing` so it accepts extra feed fields, and
add the import:

```python
from tc_core.ingest.manager_listings import ingest_manager_listings, usable_listings


def _listing(pid, name, address, city="Vancouver", **extra):
    item = {
        "id": pid, "name": name, "permalink": f"https://example.org/{pid}",
        "address": {"address": address, "city": city},
        "client": {"id": 118, "name": "Tribe Rentals"},
        "contact": {"name": "Staff Person", "phone": "604-000-0000", "email": "staff@example.org"},
    }
    item.update(extra)
    return item
```

Append these tests:

```python
def test_status_and_units_are_stored_and_the_newer_snapshot_wins(tmp_path):
    _snapshot(tmp_path, "2026-09-01", [_listing(1, "Amber Lodge", "1045 W 14th Ave", status="In Development")])
    _snapshot(tmp_path, "2026-09-30", [_listing(1, "Amber Lodge", "1045 W 14th Ave", status="Now Renting", units=120)])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    assert conn.execute("SELECT status, units FROM raw_manager_listings").fetchone() == ("Now Renting", 120)


def test_init_db_adds_the_new_columns_to_an_existing_table(tmp_path):
    conn = get_connection(":memory:")
    conn.execute(
        "CREATE TABLE raw_manager_listings (listing_row_id INTEGER PRIMARY KEY, manager TEXT NOT NULL, "
        "external_id TEXT NOT NULL, name TEXT, address TEXT, url TEXT, first_seen TEXT NOT NULL, "
        "last_seen TEXT NOT NULL, UNIQUE (manager, external_id))"
    )
    conn.execute(
        "INSERT INTO raw_manager_listings (manager, external_id, first_seen, last_seen) "
        "VALUES ('Tribe Rentals', '1', '2026-09-01', '2026-09-01')"
    )
    init_db(conn)
    init_db(conn)  # a second run must not try to add the columns again
    cols = {r[1] for r in conn.execute("PRAGMA table_info(raw_manager_listings)")}
    assert {"status", "units"} <= cols
    assert conn.execute("SELECT count(*) FROM raw_manager_listings").fetchone()[0] == 1


def test_usable_listings_are_current_and_built(tmp_path):
    _snapshot(tmp_path, "2026-09-01", [_listing(1, "Gone Manor", "1 Gone St")])
    _snapshot(tmp_path, "2026-09-30", [
        _listing(2, "Maple Apartments", "1220 Cardero Street", units=40),
        _listing(3, "Hornby & Drake", "1300 Hornby St", status=" in development "),
        _listing(4, "Next Year", "2 Future St", status="Coming Soon"),
    ])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    usable = usable_listings(conn)
    assert [u["name"] for u in usable] == ["Maple Apartments"]
    assert usable[0]["last_seen"] == "2026-09-30" and usable[0]["units"] == 40
    assert set(usable[0]) == {"listing_row_id", "manager", "name", "address", "url", "last_seen", "units"}


def test_current_is_judged_per_manager(tmp_path):
    _snapshot(tmp_path, "2026-09-24", [_listing(1, "Maple Apartments", "1220 Cardero Street")])
    other = tmp_path / "dorset"
    other.mkdir()
    (other / "2026-09-30.json").write_text(json.dumps([
        {**_listing(9, "Ocean Crest", "1333 Jervis Street"), "client": {"name": "Dorset Realty Group"}},
    ]))
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    assert sorted(u["name"] for u in usable_listings(conn)) == ["Maple Apartments", "Ocean Crest"]


def test_an_all_out_of_town_snapshot_does_not_keep_stale_listings_current(tmp_path):
    _snapshot(tmp_path, "2026-09-01", [_listing(1, "Maple Apartments", "1220 Cardero Street")])
    _snapshot(tmp_path, "2026-09-30", [_listing(2, "Glenwood", "1234 Fort Street", city="Victoria")])
    conn = _conn()
    ingest_manager_listings(conn, str(tmp_path))
    # The 2026-09-30 snapshot stored nothing, so 2026-09-01 is still this manager's latest
    # stored date: the listing stays usable. This pins the current, documented behaviour.
    assert [u["name"] for u in usable_listings(conn)] == ["Maple Apartments"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_manager_listings.py -v`
Expected: FAIL. You'll see `ImportError: cannot import name 'usable_listings'`.

- [ ] **Step 3: Add the columns to the schema**

In `src/tc_core/schema.sql`, change the `raw_manager_listings` CREATE to:

```sql
CREATE TABLE IF NOT EXISTS raw_manager_listings (
    listing_row_id INTEGER PRIMARY KEY,
    manager TEXT NOT NULL,
    external_id TEXT NOT NULL,
    name TEXT,
    address TEXT,
    url TEXT,
    status TEXT,     -- the feed's own status ("Now Renting", "In Development"); null when it has none
    units INTEGER,   -- unit count, when the feed gives one (Wall)
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    UNIQUE (manager, external_id)
);
```

- [ ] **Step 4: Add the migration to `init_db`**

In `src/tc_core/db.py`, replace `init_db` with:

```python
# Columns added to PERSISTENT tables after they first shipped. CREATE TABLE IF
# NOT EXISTS leaves an existing table as it was, so init_db adds them here.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "raw_manager_listings": [("status", "TEXT"), ("units", "INTEGER")],
}


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_db(conn: sqlite3.Connection, schema_path: str | Path = SCHEMA_PATH) -> None:
    """Load the schema.

    Safe to call repeatedly: every table except `ownership_claims` is dropped
    and recreated (schema.sql's REBUILDABLE section), while `ownership_claims`
    uses `CREATE TABLE IF NOT EXISTS` and is never touched by a rebuild.
    PERSISTENT tables that gained columns get them added (_ADDED_COLUMNS).
    """
    sql = Path(schema_path).read_text(encoding="utf-8")
    with conn:
        conn.executescript(sql)
        _add_missing_columns(conn)
```

- [ ] **Step 5: Store status/units and add `usable_listings()`**

In `src/tc_core/ingest/manager_listings.py`:

1. Docstring: replace "Only the listing's id, name, address and URL are stored:" with
   "Only the listing's id, name, address, URL, status and unit count are stored:".
2. Below `_DATE_RE`, add:

```python
# Feed statuses for buildings that don't exist yet: such a listing never adds a
# building, a link or a manager to the map.
UNBUILT_STATUSES = ("in development", "coming soon")
```

3. In `_listings`, extend the appended dict:

```python
        units = item.get("units")
        rows.append({
            "manager": (item.get("client") or {}).get("name") or path.parent.name,
            "external_id": str(item["id"]),
            "name": (item.get("name") or "").strip() or None,
            "address": (address or "").strip() or None,
            "url": item.get("permalink") or None,
            "status": (item.get("status") or "").strip() or None,
            "units": int(units) if isinstance(units, (int, float)) and units > 0 else None,
        })
```

4. Replace the upsert SQL in `ingest_manager_listings` with:

```python
                conn.execute(
                    """
                    INSERT INTO raw_manager_listings
                        (manager, external_id, name, address, url, status, units, first_seen, last_seen)
                    VALUES (:manager, :external_id, :name, :address, :url, :status, :units, :seen, :seen)
                    ON CONFLICT (manager, external_id) DO UPDATE SET
                        name = CASE WHEN :seen >= last_seen THEN excluded.name ELSE name END,
                        address = CASE WHEN :seen >= last_seen THEN excluded.address ELSE address END,
                        url = CASE WHEN :seen >= last_seen THEN excluded.url ELSE url END,
                        status = CASE WHEN :seen >= last_seen THEN excluded.status ELSE status END,
                        units = CASE WHEN :seen >= last_seen THEN excluded.units ELSE units END,
                        first_seen = min(first_seen, :seen),
                        last_seen = max(last_seen, :seen)
                    """,
                    {**row, "seen": seen},
                )
```

5. Append:

```python
def usable_listings(conn: sqlite3.Connection) -> list[dict]:
    """Listings that may add a building, a link or a manager to the map: in
    their manager's latest snapshot (a listing that dropped out stays in the
    table as history) and not for an unbuilt building."""
    marks = ", ".join("?" for _ in UNBUILT_STATUSES)
    rows = conn.execute(
        f"""
        SELECT l.listing_row_id, l.manager, l.name, l.address, l.url, l.last_seen, l.units
        FROM raw_manager_listings l
        JOIN (SELECT manager, max(last_seen) AS latest FROM raw_manager_listings GROUP BY manager) m
          ON m.manager = l.manager AND m.latest = l.last_seen
        WHERE lower(trim(coalesce(l.status, ''))) NOT IN ({marks})
        ORDER BY l.listing_row_id
        """,
        UNBUILT_STATUSES,
    ).fetchall()
    keys = ("listing_row_id", "manager", "name", "address", "url", "last_seen", "units")
    return [dict(zip(keys, r)) for r in rows]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_manager_listings.py -v`
Expected: all PASS, including the existing staff-contact and out-of-town tests.

- [ ] **Step 7: Checkpoint.** Run `uv run pytest`; expect everything to pass. Report to the user; don't commit.

---

### Task 2: Listings add buildings in the merge

**Files:**
- Create: `src/tc_core/ingest/listing_buildings.py`
- Modify: `src/tc_core/ingest/merge.py` (`BUILDING_SOURCE_ORDER` ~line 234, `merge_and_dedupe_buildings` ~line 318, `run_merge` ~line 425)
- Modify: `src/tc_core/ingest/__init__.py` (ingest order, ~lines 118–130)
- Modify: `src/tc_core/ingest/building_names.py` (`source_row_ids` may now be a dict)
- Test: `tests/test_listing_buildings.py`

**Interfaces:**
- Consumes: `usable_listings(conn)` (Task 1); `overlays._match_key`, `overlays._build_loose_index`, `overlay_sources.load_secondary_address_index`, `normalize.address_key_variants`, `merge._prepare_addresses`.
- Produces:
  - `tc_core.ingest.listing_buildings.BUILDING_SOURCE = "manager listing"`.
  - `listing_building_rows(listings: list[dict], known_keys: set[str], secondary_index: dict[str, str], addr_points: pd.DataFrame) -> pd.DataFrame`. Its columns are those of `merge._deduplicate_buildings`' output.
  - `merge_and_dedupe_buildings(raw_buildings, raw_addresses, listings=None, secondary_index=None)`.
  - A listing-created building's `source_row_ids` is `{"raw_manager_listings": [ids]}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_listing_buildings.py`:

```python
"""Usable landlord listings add the buildings the City's sources don't list,
placed on a City address point and never naming an owner (spec
2026-09-30-landlord-listings-source-design.md, section 2)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tc_core.db import get_connection, init_db
from tc_core.ingest.listing_buildings import BUILDING_SOURCE, listing_building_rows
from tc_core.ingest.merge import _prepare_addresses, load_raw_frames, merge_and_dedupe_buildings

NOW = "2026-09-30T00:00:00+00:00"


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def _point(conn, civic, street, lat, lon, area="West End"):
    conn.execute(
        "INSERT INTO raw_addresses (civic_number, std_street, geo_point_2d, geo_local_area, ingested_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (civic, street, f"{lat}, {lon}", area, NOW),
    )


def _listing(row_id, address, units=None, manager="Wall Financial Corporation"):
    return {"listing_row_id": row_id, "manager": manager, "name": None, "address": address,
            "url": f"https://example.org/{row_id}", "last_seen": "2026-09-30", "units": units}


def _points(conn):
    _, raw_addresses = load_raw_frames(conn)
    return _prepare_addresses(raw_addresses)


def test_an_unlisted_building_on_an_address_point_is_added():
    conn = _conn()
    _point(conn, "1120", "PACIFIC ST", 49.2783, -123.1335)
    rows = listing_building_rows([_listing(7, "1120 Pacific Street", units=120)], set(), {}, _points(conn))
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["addr_key"] == "1120 pacific st"
    assert (row["lat"], row["lon"]) == (49.2783, -123.1335)
    assert row["local_area"] == "West End"
    assert row["units"] == 120
    assert row["building_source"] == BUILDING_SOURCE == "manager listing"
    assert (row["owner_group"], row["owner_key"]) == ("(Unknown)", "unknown")
    assert row["source_row_ids"] == {"raw_manager_listings": [7]}


def test_a_listing_without_an_address_point_adds_nothing():
    conn = _conn()
    _point(conn, "1120", "PACIFIC ST", 49.2783, -123.1335)
    assert listing_building_rows([_listing(7, "6000 Wesbrook Mall")], set(), {}, _points(conn)).empty


def test_a_listing_matching_a_known_building_adds_nothing_even_by_street_type_typo():
    conn = _conn()
    _point(conn, "1333", "JERVIS ST", 49.28, -123.13)
    known = {"1333 jervis st"}
    rows = listing_building_rows([_listing(1, "1333 Jervis Avenue")], known, {}, _points(conn))
    assert rows.empty


def test_a_listing_at_a_secondary_address_adds_nothing():
    conn = _conn()
    _point(conn, "936", "BUTE ST", 49.28, -123.13)
    rows = listing_building_rows(
        [_listing(1, "936 Bute Street")], {"958 bute st"}, {"936 bute st": "958 bute st"}, _points(conn),
    )
    assert rows.empty


def test_two_companies_listing_one_new_address_make_one_building():
    conn = _conn()
    _point(conn, "455", "ABBOTT ST", 49.28, -123.10)
    rows = listing_building_rows(
        [_listing(3, "455 Abbott Street", units=80, manager="Tribe Rentals"),
         _listing(4, "455 Abbott St", units=82)],
        set(), {}, _points(conn),
    )
    assert len(rows) == 1
    assert rows.iloc[0]["units"] == 82
    assert rows.iloc[0]["source_row_ids"] == {"raw_manager_listings": [3, 4]}


def test_city_sources_win_and_listings_fill_the_gaps():
    conn = _conn()
    _point(conn, "1220", "CARDERO ST", 49.29, -123.14)
    _point(conn, "1120", "PACIFIC ST", 49.2783, -123.1335)
    conn.execute(
        "INSERT INTO raw_buildings (raw_building_id, address, local_area, units, building_source, ingested_at) "
        "VALUES (1, '1220 cardero st', 'West End', 30, 'rental licence', ?)", (NOW,),
    )
    raw_buildings, raw_addresses = load_raw_frames(conn)
    out = merge_and_dedupe_buildings(
        raw_buildings, raw_addresses,
        listings=[_listing(1, "1220 Cardero Street", units=99), _listing(2, "1120 Pacific Street")],
        secondary_index={},
    )
    by_key = {r["addr_key"]: r for _, r in out.iterrows()}
    assert set(by_key) == {"1220 cardero st", "1120 pacific st"}
    assert by_key["1220 cardero st"]["building_source"] == "rental licence"
    assert by_key["1220 cardero st"]["units"] == 30
    assert by_key["1120 pacific st"]["building_source"] == "manager listing"


def test_merge_without_listings_is_unchanged():
    conn = _conn()
    _point(conn, "1220", "CARDERO ST", 49.29, -123.14)
    conn.execute(
        "INSERT INTO raw_buildings (raw_building_id, address, local_area, ingested_at) "
        "VALUES (1, '1220 cardero st', 'West End', ?)", (NOW,),
    )
    raw_buildings, raw_addresses = load_raw_frames(conn)
    assert list(merge_and_dedupe_buildings(raw_buildings, raw_addresses)["addr_key"]) == ["1220 cardero st"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_listing_buildings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tc_core.ingest.listing_buildings'`.

- [ ] **Step 3: Create `src/tc_core/ingest/listing_buildings.py`**

```python
"""Buildings from landlord listings: the fourth building source, ranked last.

A usable listing (manager_listings.usable_listings) adds a building only
when no building from the City's sources matches it, by the same matching
building names use (overlays._match_key, so a street-type typo or a
secondary entrance still lands on the City's building), and its address is
a City address point, which places it. Listings never name an owner: the
building's owner is "(Unknown)" until the registry or a licence says more.
"""

from __future__ import annotations

import pandas as pd

from ..normalize import address_key_variants, sanitize_owner
from .overlays import _build_loose_index, _match_key

BUILDING_SOURCE = "manager listing"

_COLUMNS = [
    "address", "lat", "lon", "units", "building_source", "year_built", "n_issues",
    "issues_details", "value_land", "value_bldg", "bldg_land_ratio", "owner_group",
    "owner_key", "local_area", "source_row_ids", "addr_key",
]


def listing_building_rows(
    listings: list[dict],
    known_keys: set[str],
    secondary_index: dict[str, str],
    addr_points: pd.DataFrame,
) -> pd.DataFrame:
    """New building rows, shaped like merge._deduplicate_buildings' output.
    addr_points is merge._prepare_addresses' frame (addr_key, lat, lon,
    geo_local_area). Listings at one address make one building."""
    loose = _build_loose_index(known_keys)
    points = (
        addr_points.dropna(subset=["lat", "lon"])
        .drop_duplicates("addr_key")
        .set_index("addr_key")
    )
    found: dict[str, dict] = {}
    for listing in listings:
        address = listing.get("address")
        if not address:
            continue
        if _match_key(address, known_keys, secondary_index, loose) in known_keys:
            continue
        key = next((k for k in address_key_variants(address) if k in points.index), None)
        if key is None:
            continue
        rec = found.setdefault(key, {"ids": [], "units": []})
        rec["ids"].append(int(listing["listing_row_id"]))
        if listing.get("units"):
            rec["units"].append(int(listing["units"]))

    rows = []
    for key, rec in found.items():
        point = points.loc[key]
        area = point.get("geo_local_area")
        rows.append({
            "address": key,
            "lat": float(point["lat"]),
            "lon": float(point["lon"]),
            "units": float(max(rec["units"])) if rec["units"] else None,
            "building_source": BUILDING_SOURCE,
            "year_built": None,
            "n_issues": None,
            "issues_details": None,
            "value_land": None,
            "value_bldg": None,
            "bldg_land_ratio": None,
            "owner_group": "(Unknown)",
            "owner_key": sanitize_owner("(Unknown)"),
            "local_area": area.strip() if isinstance(area, str) and area.strip() else "(Unknown)",
            "source_row_ids": {"raw_manager_listings": sorted(rec["ids"])},
            "addr_key": key,
        })
    return pd.DataFrame(rows, columns=_COLUMNS)
```

- [ ] **Step 4: Wire it into the merge**

In `src/tc_core/ingest/merge.py`:

1. Add these imports after the `..normalize` import block:

```python
from .listing_buildings import BUILDING_SOURCE as LISTING_SOURCE, listing_building_rows
from .manager_listings import usable_listings
from .overlay_sources import load_secondary_address_index
```

   If importing `.listing_buildings` at module level raises a circular-import error
   (`overlays` → … → `merge`), move these three imports inside the functions that use them.

2. Replace `BUILDING_SOURCE_ORDER`:

```python
# Landlord listings come last: they add buildings no City source lists, and never win a merge.
BUILDING_SOURCE_ORDER = ("rental inventory", "non-market housing list", "rental licence", LISTING_SOURCE)
```

3. Replace `merge_and_dedupe_buildings`:

```python
def merge_and_dedupe_buildings(
    raw_buildings: pd.DataFrame,
    raw_addresses: pd.DataFrame,
    listings: list[dict] | None = None,
    secondary_index: dict[str, str] | None = None,
) -> pd.DataFrame:
    addr_df = _prepare_addresses(raw_addresses)
    west, owner_col = _select_buildings(raw_buildings)
    joined = _join_buildings_addresses(west, addr_df)
    buildings = _deduplicate_buildings(joined, owner_col)
    if listings:
        known = set(buildings["addr_key"]) if "addr_key" in buildings.columns else set()
        extra = listing_building_rows(listings, known, secondary_index or {}, addr_df)
        if not extra.empty:
            buildings = pd.concat([buildings, extra], ignore_index=True)
    return buildings
```

4. In `run_merge`, replace the first two lines with:

```python
    raw_buildings, raw_addresses = load_raw_frames(conn)
    listings = usable_listings(conn)
    secondary = load_secondary_address_index(conn) if listings else {}
    buildings_df = merge_and_dedupe_buildings(raw_buildings, raw_addresses, listings, secondary)
```

- [ ] **Step 5: Tolerate dict lineage in building names**

In `src/tc_core/ingest/building_names.py`, `derive_building_names`, replace
`for raw_id in json.loads(source_ids or "[]"):` with:

```python
        ids = json.loads(source_ids or "[]")
        # A building added from a listing records {"raw_manager_listings": [...]}.
        for raw_id in ids if isinstance(ids, list) else []:
```

- [ ] **Step 6: Ingest listings before the merge**

In `src/tc_core/ingest/__init__.py`, `run_ingest`: move the two blocks below so they sit
just before `counts["buildings"] = run_source(conn, run_id, "buildings", run_merge, conn)`.
Leave the blocks' contents as they are.
- the `if config.manager_listings:` block, which ingests `raw_manager_listings`;
- the `if config.strata_lot_pids:` block.

Add the comment `# Raw inputs the merge reads: listings add buildings (ingest/listing_buildings.py).`
above them.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_listing_buildings.py tests/test_building_names.py -v`
Expected: all PASS.
Then run: `uv run pytest`
Expected: all PASS. If `tests/test_rebuild_data.py` asserts the ingest order, update that
expected order to match Step 6.

- [ ] **Step 8: Checkpoint.** Report to the user; don't commit.

---

### Task 3: `building_listings` link table and the rebuild log

**Files:**
- Modify: `src/tc_core/schema.sql` (REBUILDABLE drop list, top of file; new CREATE after `building_names`, ~line 297)
- Modify: `src/tc_core/ingest/building_names.py`
- Modify: `src/tc_core/ingest/listing_buildings.py` (add `added_from_listings`)
- Modify: `scripts/rebuild_data.py`
- Test: `tests/test_building_names.py`, `tests/test_listing_buildings.py`

**Interfaces:**
- Consumes: `usable_listings(conn)` (Task 1); `BUILDING_SOURCE` (Task 2).
- Produces:
  - Table `building_listings(building_listing_id, building_id, manager, url, last_seen, listing_row_id)`.
  - `listing_buildings.added_from_listings(conn) -> list[tuple[str, str]]`, returning
    `(manager, address)` pairs sorted by manager, then address.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_building_names.py`:

```python
def _listing_row(conn, row_id, address, last_seen, status=None, manager="Tribe Rentals"):
    conn.execute(
        "INSERT INTO raw_manager_listings (listing_row_id, manager, external_id, name, address, url, status, "
        "first_seen, last_seen) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?)",
        (row_id, manager, str(row_id), address, f"https://example.org/{row_id}", status, last_seen, last_seen),
    )


def test_usable_listings_link_to_their_building():
    conn = _conn()
    _building(conn, 1, "1220 cardero st", 1)
    _listing_row(conn, 1, "1220 Cardero Street", "2026-09-30")
    _listing_row(conn, 2, "1220 Cardero Street", "2026-09-01")                # stale
    _listing_row(conn, 3, "1220 Cardero Street", "2026-09-30", "In Development")
    _listing_row(conn, 4, "9 Elsewhere St", "2026-09-30")                     # no building
    derive_building_names(conn)
    assert conn.execute(
        "SELECT building_id, manager, url, last_seen, listing_row_id FROM building_listings"
    ).fetchall() == [(1, "Tribe Rentals", "https://example.org/1", "2026-09-30", 1)]
```

Append to `tests/test_listing_buildings.py`:

```python
def test_added_from_listings_names_each_added_building_and_its_lister():
    from tc_core.ingest.listing_buildings import added_from_listings

    conn = _conn()
    conn.executemany(
        "INSERT INTO buildings (building_id, addr_key, address, building_source, source_row_ids, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, '[]', ?, ?)",
        [(1, "1120 pacific st", "1120 pacific st", "manager listing", NOW, NOW),
         (2, "1220 cardero st", "1220 cardero st", "rental licence", NOW, NOW)],
    )
    conn.executemany(
        "INSERT INTO building_listings (building_id, manager, url, last_seen, listing_row_id) VALUES (?, ?, ?, ?, ?)",
        [(1, "Wall Financial Corporation", "https://example.org/1", "2026-09-30", 1),
         (2, "Tribe Rentals", "https://example.org/2", "2026-09-30", 2)],
    )
    assert added_from_listings(conn) == [("Wall Financial Corporation", "1120 pacific st")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_building_names.py tests/test_listing_buildings.py -v`
Expected: FAIL with `sqlite3.OperationalError: no such table: building_listings`.

- [ ] **Step 3: Add the table**

In `src/tc_core/schema.sql`:

1. Directly under `DROP TABLE IF EXISTS building_names;  -- references buildings: drop first`, add:

```sql
DROP TABLE IF EXISTS building_listings;  -- references buildings: drop first
```

2. Directly after `CREATE INDEX idx_building_names_building ON building_names(building_id);`, add:

```sql
-- Usable landlord listings (current, built: manager_listings.usable_listings)
-- matched to buildings by ingest/building_names.py. The export's `listings`
-- column and listing-based managed_by read this.
CREATE TABLE building_listings (
    building_listing_id INTEGER PRIMARY KEY,
    building_id INTEGER NOT NULL REFERENCES buildings(building_id),
    manager TEXT NOT NULL,      -- the feed's company name, verbatim
    url TEXT,
    last_seen TEXT NOT NULL,
    listing_row_id INTEGER NOT NULL
);
CREATE INDEX idx_building_listings_building ON building_listings(building_id);
```

- [ ] **Step 4: Write the links in `derive_building_names`**

In `src/tc_core/ingest/building_names.py`:

1. Add the import `from .manager_listings import usable_listings`.
2. Docstring: append the sentence "Usable listings are also linked to their building in
   building_listings."
3. After the existing `for row_id, name, address in conn.execute(...)` loop, add:

```python
    links = []
    for listing in usable_listings(conn):
        if not listing["address"]:
            continue
        key = _match_key(listing["address"], known, secondary, loose)
        if key in by_key:
            links.append((by_key[key], listing["manager"], listing["url"],
                          listing["last_seen"], listing["listing_row_id"]))
```

4. Extend the final `with conn:` block:

```python
    with conn:
        conn.execute("DELETE FROM building_names")
        conn.executemany(
            "INSERT INTO building_names (building_id, name, source_type, source_table, source_row_id) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute("DELETE FROM building_listings")
        conn.executemany(
            "INSERT INTO building_listings (building_id, manager, url, last_seen, listing_row_id) "
            "VALUES (?, ?, ?, ?, ?)",
            links,
        )
    return len(rows)
```

- [ ] **Step 5: Add `added_from_listings`**

Append to `src/tc_core/ingest/listing_buildings.py`:

```python
def added_from_listings(conn) -> list[tuple[str, str]]:
    """(manager, address) for every building a listing added, for the rebuild
    log: a listing for something that isn't rental housing shows up here."""
    return conn.execute(
        """
        SELECT DISTINCT bl.manager, b.address
        FROM buildings b JOIN building_listings bl ON bl.building_id = b.building_id
        WHERE b.building_source = ?
        ORDER BY bl.manager, b.address
        """,
        (BUILDING_SOURCE,),
    ).fetchall()
```

- [ ] **Step 6: Print the log in the rebuild**

In `scripts/rebuild_data.py`:
1. Add the import `from tc_core.ingest.listing_buildings import added_from_listings`. Put
   it next to the other `tc_core` imports, matching their style.
2. Directly after `print(f"Ingest complete: {counts}")`, add:

```python
        added = added_from_listings(conn)
        if added:
            print(f"{len(added)} building(s) added from landlord listings; check each is rental housing:")
            for manager, address in added:
                print(f"  {manager}: {address}")
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest`
Expected: all PASS.

- [ ] **Step 8: Checkpoint.** Report to the user; don't commit.

---

### Task 4: Export `listings`, `managed_by_source` and the listing rule

**Files:**
- Modify: `src/tc_core/export.py` (`reconstruct_points` ~line 45–100, `load_property_managers` ~206, `apply_property_managers` ~224, `export_artifacts` ~650–670, `BUILDING_RECORD_COLUMNS` ~806)
- Modify: `frontend/fixtures/*` (regenerated by script)
- Test: `tests/test_export_property_managers.py`, `tests/test_export_ownership.py`

**Interfaces:**
- Consumes: the `building_listings` table (Task 3).
- Produces:
  - `export.load_listing_aliases(path: str | None) -> dict[str, str]`, mapping
    `sanitize_owner(feed name)` to the toml manager name.
  - `export._load_building_listings(conn, aliases) -> dict[int, list[dict]]`.
  - `reconstruct_points(conn, now, pid_address_map_path=None, property_managers=None, listing_aliases=None)`.
  - `apply_property_managers(df, managers)` is unchanged in signature. It now also writes
    `managed_by_source`, and fills `managed_by` from `df["listings"]` when that column exists.
  - Record columns `managed_by_source` and `listings`, which follow `managed_by`.

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/test_export_property_managers.py`:

```python
LISTED = [{"by": TRIBE, "url": "https://example.org/1", "seen": "2026-09-30"}]


def test_a_licence_named_manager_is_marked_as_coming_from_the_licence():
    row = _apply(_row(listings=LISTED)).iloc[0]
    assert (row.managed_by, row.managed_by_source) == (TRIBE, "licence")


def test_a_managers_current_listing_names_it_without_touching_the_owner():
    row = _apply(_row(
        owner_name="Broadway Properties Ltd.", owner_key="broadway-properties-ltd", owner_source="registry",
        licence_holder="Broadway Properties Ltd.",
        network_name="Broadway Properties Ltd.", network_key="broadway-properties-ltd", network_source="registry",
        listings=LISTED,
    )).iloc[0]
    assert (row.managed_by, row.managed_by_source) == (TRIBE, "listing")
    assert (row.owner_name, row.owner_source) == ("Broadway Properties Ltd.", "registry")
    assert (row.network_key, row.network_source) == ("broadway-properties-ltd", "registry")


def test_a_listing_by_a_company_not_in_the_managers_list_sets_no_manager():
    row = _apply(_row(
        owner_name="0888189 B.C. Ltd.", owner_key="0888189-b-c-ltd", owner_source="registry",
        licence_holder="0888189 BC Ltd", network_key="0888189-b-c-ltd", network_source="registry",
        listings=[{"by": "Wall Financial Corporation", "url": "https://example.org/w", "seen": "2026-09-30"}],
    )).iloc[0]
    assert row.managed_by is None and row.managed_by_source is None
    assert row.owner_name == "0888189 B.C. Ltd."


def test_load_listing_aliases_maps_feed_names_to_the_managers_name(tmp_path):
    from tc_core.export import load_listing_aliases

    path = tmp_path / "property_managers.toml"
    path.write_text(
        '[[manager]]\nname = "Tribe Rental Management"\nlisting_names = ["Tribe Rentals"]\n\n'
        '[[manager]]\nname = "Dorset Realty Group"\n'
    )
    assert load_listing_aliases(str(path)) == {
        "tribe-rentals": "Tribe Rental Management",
        "tribe-rental-management": "Tribe Rental Management",
        "dorset-realty-group": "Dorset Realty Group",
    }
    assert load_listing_aliases(None) == {}
```

- [ ] **Step 2: Write the failing export test**

In `tests/test_export_ownership.py`, change `_export` to pass keyword arguments through:

```python
def _export(tmp_path: Path, extra=None, **kwargs) -> Path:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    pid_map = _seed(conn, tmp_path)
    if extra:
        extra(conn)
    out = tmp_path / "out"
    export_artifacts(conn, out, pid_address_map_path=pid_map, **kwargs)
    return out
```

Then append:

```python
def test_listings_reach_the_record_under_the_managers_own_name(tmp_path):
    managers = tmp_path / "property_managers.toml"
    managers.write_text('[[manager]]\nname = "Tribe Rental Management"\nlisting_names = ["Tribe Rentals"]\n')

    def extra(conn):
        bid = conn.execute("SELECT building_id FROM buildings WHERE addr_key = '1 solo st'").fetchone()[0]
        conn.executemany(
            "INSERT INTO building_listings (building_id, manager, url, last_seen, listing_row_id) VALUES (?, ?, ?, ?, ?)",
            [(bid, "Tribe Rentals", "https://example.org/1", "2026-09-30", 1),
             (bid, "Wall Financial Corporation", "https://example.org/w", "2026-09-30", 2)],
        )

    records = _records(_export(tmp_path, extra, property_managers_path=str(managers)))
    rec = records["1 solo st"]
    assert rec["listings"] == [
        {"by": "Tribe Rental Management", "url": "https://example.org/1", "seen": "2026-09-30"},
        {"by": "Wall Financial Corporation", "url": "https://example.org/w", "seen": "2026-09-30"},
    ]
    assert (rec["managed_by"], rec["managed_by_source"]) == ("Tribe Rental Management", "listing")
    assert rec["owner_name"] == "Solo Rentals Ltd"
    # unlisted buildings and overlay records carry an empty list, never null
    assert records["2 solo st"]["listings"] == [] and records["999 nowhere rd"]["listings"] == []
    assert records["2 solo st"]["managed_by_source"] is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_export_property_managers.py tests/test_export_ownership.py -v`
Expected: FAIL.
- The unit tests fail with `AttributeError: ... 'managed_by_source'` or an ImportError for `load_listing_aliases`.
- The export test fails with a `KeyError: 'listings'`.

- [ ] **Step 4: Implement the loaders**

In `src/tc_core/export.py`, below `load_property_managers`, add:

```python
def load_listing_aliases(path: str | None) -> dict[str, str]:
    """Feed company name key -> the manager's name in property_managers.toml.
    A feed may name the company differently ("Tribe Rentals"); an entry lists
    those names as listing_names = [...]. Each entry's own name maps to itself."""
    if not path or not Path(path).exists():
        return {}
    data = tomllib.loads(Path(path).read_text())
    aliases: dict[str, str] = {}
    for m in data.get("manager", []):
        name = m.get("name")
        if not name:
            continue
        for alias in [name, *m.get("listing_names", [])]:
            aliases[sanitize_owner(alias)] = name
    return aliases


def _load_building_listings(
    conn: sqlite3.Connection, aliases: dict[str, str]
) -> dict[int, list[dict]]:
    """building_id -> [{by, url, seen}], one entry per company, a known
    manager under its property_managers.toml name. Public: each is the
    company's own page. Listing ids stay in the database."""
    out: dict[int, list[dict]] = {}
    try:
        rows = conn.execute(
            "SELECT building_id, manager, url, last_seen FROM building_listings "
            "ORDER BY building_id, listing_row_id"
        ).fetchall()
    except sqlite3.OperationalError:  # a database built before building_listings existed
        return out
    for bid, manager, url, seen in rows:
        by = aliases.get(sanitize_owner(manager), manager)
        entries = out.setdefault(int(bid), [])
        if not any(e["by"] == by for e in entries):
            entries.append({"by": by, "url": url, "seen": seen})
    return out
```

- [ ] **Step 5: Extend `apply_property_managers`**

Replace the function with:

```python
def apply_property_managers(df: pd.DataFrame, managers: set[str]) -> None:
    """A rental licence held by a known property manager names who runs the
    building, not who owns it (Tribe Rental Management holds licences for
    Greenbrier Holdings' buildings). In place: records the manager in
    `managed_by`; where the licence was the only source for the landlord,
    the building becomes not on record instead. Registry owners and claims
    groups are kept. Otherwise a known manager's current listing names the
    manager (`managed_by_source` "listing") and changes nothing else.
    """
    licence_keys = df["licence_holder"].map(sanitize_owner)
    managed = licence_keys.isin(managers)
    df["managed_by"] = df["licence_holder"].where(managed, None).astype(object)
    df["managed_by_source"] = pd.Series(
        np.where(managed, "licence", None), index=df.index, dtype=object
    )
    owner = managed & (df["owner_source"] == "licence")
    df.loc[owner, ["owner_name", "owner_key"]] = ["(Unknown)", "unknown"]
    df.loc[owner, "owner_source"] = None
    # A group that came from the manager's licence falls back to the landlord
    # itself (a group of one), or to not on record when there is none.
    group = managed & (df["network_source"] == "licence")
    df.loc[group, "network_name"] = df.loc[group, "owner_name"]
    df.loc[group, "network_key"] = df.loc[group, "owner_key"]
    df.loc[group, "network_source"] = df.loc[group, "owner_source"]
    if "listings" not in df.columns:
        return
    listed = pd.Series(
        [
            next(
                (e["by"] for e in (ls if isinstance(ls, list) else [])
                 if sanitize_owner(e["by"]) in managers),
                None,
            )
            for ls in df["listings"]
        ],
        index=df.index,
        dtype=object,
    )
    fill = df["managed_by"].isna() & listed.notna()
    df.loc[fill, "managed_by"] = listed[fill]
    df.loc[fill, "managed_by_source"] = "listing"
```

- [ ] **Step 6: Thread it through `reconstruct_points` and `export_artifacts`**

1. Change the `reconstruct_points` signature to:

```python
def reconstruct_points(
    conn: sqlite3.Connection,
    now: pd.Timestamp,
    pid_address_map_path: str | None = None,
    property_managers: set[str] | None = None,
    listing_aliases: dict[str, str] | None = None,
) -> pd.DataFrame:
```

2. Directly before `apply_property_managers(merged, property_managers or set())`, add:

```python
    building_listings = _load_building_listings(conn, listing_aliases or {})
    merged["listings"] = [building_listings.get(int(b), []) for b in merged["b_id"]]
```

3. In the column selection list that follows, replace `"licence_holder", "managed_by",` with
   `"licence_holder", "managed_by", "managed_by_source", "listings",`.

4. Directly after `merged = _append_overlay_housing(conn, merged)`, add:

```python
    # Overlay records have no listings; keep the column a list throughout.
    merged["listings"] = [v if isinstance(v, list) else [] for v in merged["listings"]]
```

5. In `export_artifacts`, replace the `reconstruct_points(...)` call with:

```python
    points_df = reconstruct_points(
        conn, now, pid_address_map_path,
        load_property_managers(property_managers_path) | managers_from_claims(conn),
        load_listing_aliases(property_managers_path),
    )
```

6. In `BUILDING_RECORD_COLUMNS`, replace `"registry_retrieved", "licence_holder", "managed_by",` with
   `"registry_retrieved", "licence_holder", "managed_by", "managed_by_source", "listings",`.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_export_property_managers.py tests/test_export_ownership.py tests/test_export_artifacts.py -v`
Expected: all PASS.

- [ ] **Step 8: Regenerate the frontend fixtures**

Run: `uv run python scripts/make_frontend_fixtures.py`
Then: `git diff --stat frontend/fixtures/`. This is read-only, which is allowed.
Expected: only `building_records.json` changes, by adding `managed_by_source`/`listings`
to its columns and records. Run `uv run pytest`; expect all PASS, including
`tests/test_frontend_fixtures.py`.

- [ ] **Step 9: Checkpoint.** Report to the user; don't commit.

---

### Task 5: Sensitivity check on listing fields

**Files:**
- Test: `tests/test_export_ownership.py`

**Interfaces:**
- Consumes: Task 4's export and Task 1's ingest.

- [ ] **Step 1: Write the test**

Append to `tests/test_export_ownership.py`:

```python
def test_feed_staff_contacts_never_reach_any_artifact(tmp_path):
    """Snapshots carry staff contacts; only the company's name, page and date
    may reach the map (spec 2026-09-30 section 5)."""
    import json as _json

    from tc_core.ingest.building_names import derive_building_names
    from tc_core.ingest.manager_listings import ingest_manager_listings

    feeds = tmp_path / "feeds" / "tribe"
    feeds.mkdir(parents=True)
    (feeds / "2026-09-30.json").write_text(_json.dumps([{
        "id": 1, "name": "Solo Place", "permalink": "https://example.org/1",
        "address": {"address": "1 Solo St", "city": "Vancouver"},
        "client": {"name": "Tribe Rentals"},
        "contact": {"name": "CANARY-staff Person", "email": "canary-staff@example.org"},
    }]))

    def extra(conn):
        ingest_manager_listings(conn, str(tmp_path / "feeds"))
        derive_building_names(conn)

    out = _export(tmp_path, extra)
    for path in out.iterdir():
        assert "canary-staff" not in path.read_text(encoding="utf-8").lower(), path.name
    rec = _records(out)["1 solo st"]
    assert [set(e) for e in rec["listings"]] == [{"by", "url", "seen"}]
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_export_ownership.py -v`
Expected: PASS. This is a guard: it should pass straight away, because Tasks 1–4 already
filter contacts. If it fails, a contact leaked. Fix the leak; never relax the test.

- [ ] **Step 3: Checkpoint.** Report to the user; don't commit.

---

### Task 6: Popup — "Listed by" links, listing provenance, "Added from"

**Files:**
- Modify: `frontend/src/provenance.ts`
- Modify: `frontend/src/popup.ts` (`ownershipLines` ~line 44, `renderPopup` facts ~line 96)
- Test: `frontend/src/popup.test.ts`, `frontend/src/landlord-picker.test.ts`

**Interfaces:**
- Consumes: the record fields `listings`, `managed_by_source` and `building_source === 'manager listing'` (Task 4).
- Produces: `provenance.listingProvenance(seen: string): string`.

- [ ] **Step 1: Write the failing tests**

Append inside `describe('renderPopup', ...)` in `frontend/src/popup.test.ts`:

```ts
  const dorset = { by: 'Dorset Realty Group', url: 'https://dorsetrealty.com/properties/residential/ocean-crest/', seen: '2026-09-30' };
  const wall = { by: 'Wall Financial Corporation', url: 'https://www.wallfinancialcorporation.com/properties/amber-lodge', seen: '2026-09-30' };

  it('links a manager named by its own listing, with the website as provenance', () => {
    const html = renderPopup({ ...building, managed_by: 'Dorset Realty Group', managed_by_source: 'listing', listings: [dorset] });
    expect(html).toContain(
      'Managed by <a href="https://dorsetrealty.com/properties/residential/ocean-crest/" target="_blank" rel="noopener">Dorset Realty Group ↗</a>',
    );
    expect(html).toContain('data-tip="Company website, seen 2026-09-30"');
    expect(html).not.toContain('Listed by');
  });

  it('keeps the licence provenance when the licence names the manager, and links its listing', () => {
    const tribe = { by: 'Tribe Rental Management', url: 'https://example.org/1', seen: '2026-09-30' };
    const html = renderPopup(
      { ...building, licence_holder: 'Tribe Rental Management', managed_by: 'Tribe Rental Management', managed_by_source: 'licence', listings: [tribe] },
      { licenceYear: 2026 },
    );
    expect(html).toContain('Managed by <a href="https://example.org/1" target="_blank" rel="noopener">Tribe Rental Management ↗</a>');
    expect(html).toContain('data-tip="City of Vancouver business licence, 2026"');
  });

  it('shows an owner-operator\'s listing as "Listed by", without a manager', () => {
    const html = renderPopup({ ...building, listings: [wall] });
    expect(html).toContain(
      'Listed by <a href="https://www.wallfinancialcorporation.com/properties/amber-lodge" target="_blank" rel="noopener">Wall Financial Corporation ↗</a>',
    );
    expect(html).not.toContain('Managed by');
  });

  it('lists the company on a not-on-record building too', () => {
    const html = renderPopup({ b_id: 9, address: '1120 pacific st', owner_name: '(Unknown)', owner_key: 'unknown', listings: [wall] });
    expect(html).toContain('Landlord not on record');
    expect(html).toContain('Listed by <a href=');
  });

  it('never links a listing URL that is not http(s)', () => {
    const html = renderPopup({ ...building, listings: [{ by: 'Evil Co', url: 'javascript:alert(1)', seen: '2026-09-30' }] });
    expect(html).toContain('Listed by Evil Co');
    expect(html).not.toContain('javascript:');
  });

  it('says a building comes from a company\'s listings, with plain units', () => {
    const html = renderPopup({
      b_id: 9, address: '1120 pacific st', owner_name: '(Unknown)', owner_key: 'unknown',
      building_source: 'manager listing', units: 120, listings: [wall],
    });
    expect(html).toContain('120 units');
    expect(html).not.toContain('licensed units');
    expect(html).toContain('Added from Wall Financial Corporation&#39;s listings');
  });
```

Before relying on the `&#39;` in the last test, check `ESCAPES` in `frontend/src/html.ts`.
If it escapes `'` to a different entity, use that entity in the assertion.

Append to `frontend/src/landlord-picker.test.ts`. Use the file's existing `rec` helper and
its `buildOptions` import.

```ts
it('counts a building whose manager comes from its listing under that manager', () => {
  const options = buildOptions([
    rec({ owner_key: 'wall', owner_name: 'W', managed_by: 'Dorset Realty Group', managed_by_source: 'listing' }),
  ]);
  const manager = options.find((o) => o.kind === 'manager');
  expect(manager?.label).toBe('Dorset Realty Group');
  expect(manager?.buildings).toBe(1);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- src/popup.test.ts src/landlord-picker.test.ts`
Expected:
- The new popup tests FAIL: there's no `<a` and no "Listed by".
- The picker test PASSES already. It pins existing behaviour, which is expected.

- [ ] **Step 3: Add `listingProvenance`**

In `frontend/src/provenance.ts`, below `licenceProvenance`, add:

```ts
/** A listing on the company's own website, by the date it was last seen there. */
export function listingProvenance(seen: string): string {
  return seen ? `Company website, seen ${seen}` : 'Company website';
}
```

- [ ] **Step 4: Render listings in the popup**

In `frontend/src/popup.ts`:

1. Extend the provenance import with `listingProvenance`.
2. Above `function ownershipLines`, add:

```ts
interface Listing { by: string; url: string | null; seen: string }

/** The building's listings ({by, url, seen}), with any non-http(s) URL dropped. */
function listingsOf(r: BuildingRecord): Listing[] {
  if (!Array.isArray(r.listings)) return [];
  return r.listings.flatMap((v) => {
    if (!v || typeof v !== 'object') return [];
    const o = v as Record<string, unknown>;
    const by = str(o.by);
    return by ? [{ by, url: safeUrl(o.url), seen: str(o.seen) }] : [];
  });
}

const linked = (text: string, url: string | null): string =>
  url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(text)} ↗</a>` : escapeHtml(text);
```

3. In `ownershipLines`, replace the `const manager = ...` / `const managerLine = ...` lines with:

```ts
  const manager = str(r.managed_by);
  const listings = listingsOf(r);
  // The manager's own listing links from its line instead of a second "Listed by".
  const own = manager ? listings.find((l) => sameName(l.by, manager)) : undefined;
  const managerProvenance = str(r.managed_by_source) === 'listing'
    ? listingProvenance(own?.seen ?? '')
    : licenceProvenance(ctx.licenceYear);
  const managerLine = () =>
    div('', `Managed by ${linked(manager, own?.url ?? null)}` + provenance(managerProvenance));
  const listedLines = listings
    .filter((l) => l !== own)
    .map((l) => div('', `Listed by ${linked(l.by, l.url)}` + provenance(listingProvenance(l.seen))));
```

4. In the not-on-record branch, change it to:

```ts
  if (!owner) {
    lines.push(div('popup-owner popup-muted', 'Landlord not on record'));
    if (manager) lines.push(managerLine());
    lines.push(...listedLines);
    return lines;
  }
```

5. In the owner branch, directly after the `if (manager) lines.push(managerLine()); else if (...) { ...Licensed as... }`
   statement, add `lines.push(...listedLines);`.

6. In `renderPopup`, directly after `if (sizeLine) facts.push(div('', escapeHtml(sizeLine)));`, add:

```ts
  if (str(r.building_source) === 'manager listing') {
    const by = listingsOf(r)[0]?.by;
    facts.push(div('popup-muted', escapeHtml(by ? `Added from ${by}'s listings` : "Added from a landlord's listings")));
  }
```

- [ ] **Step 5: Run the tests and typecheck**

Run: `cd frontend && npm test && npm run typecheck`
Expected: all PASS, with no type errors. The existing "Managed by Tribe Rental Management<span class="prov"" assertion
must still pass, because without a listing `linked()` returns plain escaped text.

- [ ] **Step 6: Checkpoint.** Report to the user; don't commit.

---

### Task 7: MetCap Living scraper

**Files:**
- Create: `scripts/fetch_metcap_listings.py`
- Test: `tests/test_fetch_metcap_listings.py`
- Modify: `data/raw/property_managers/MANIFEST.md`

**Interfaces:**
- Produces: `data/raw/property_managers/metcap/<YYYY-MM-DD>.json` in the shared feed shape
  `{id, name, permalink, address: {address, city, lat, lon}, client: {name}}`.

Source: `https://www.metcap.com/province-search-results?lang=en&province=117&city=Vancouver`.
On 2026-09-30 it served 23 server-rendered cards on one page, with no pagination. Each card
looks like this:

```html
<div class="province-results__item" style="cursor: pointer;" onclick="centerMap($(this), {lat: 49.2849601, lon: -123.1322621})">
  ...
  <h2><a href="/property/1005-jervis-street-vancouver-bc-v6e-3t1">1005 Jervis Street, Vancouver, BC V6E 3T1</a></h2>
  <p>
    <span class="d-block">The Summit</span>
    <span class="d-block"><a href="/apartment/1-bedroom-22">Vancouver 1 Bedroom from $2,275.00</a></span>
  </p>
```

A card may have no plain-text name span; then `name` is null. Cards carry no staff contacts.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fetch_metcap_listings.py`:

```python
"""MetCap Living's Vancouver search page parses into the shared feed shape."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "fetch_metcap_listings",
    Path(__file__).resolve().parent.parent / "scripts" / "fetch_metcap_listings.py",
)
metcap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metcap)

CARD = """
<div class="province-results__item" style="cursor: pointer;" onclick="centerMap($(this), {lat: 49.2849601, lon: -123.1322621})">
  <div class="province-results__content">
    <h2><a href="/property/1005-jervis-street-vancouver-bc-v6e-3t1">1005 Jervis Street, Vancouver, BC V6E 3T1</a></h2>
    <p>
      <span class="d-block">The Summit</span>
      <span class="d-block"><a href="/apartment/1-bedroom-22">Vancouver 1 Bedroom from $2,275.00</a></span>
    </p>
  </div>
</div>
<div class="province-results__item" style="cursor: pointer;" onclick="centerMap($(this), {lat: 49.29, lon: -123.14})">
  <div class="province-results__content">
    <h2><a href="/property/1265-cardero-street-vancouver-bc-v6g-2j2">1265 Cardero Street, Vancouver, BC V6G 2J2</a></h2>
    <p>
      <span class="d-block"><a href="/apartment/x">Vancouver Bachelor from $1,999.00</a></span>
    </p>
  </div>
</div>
"""


def test_cards_parse_into_the_feed_shape():
    listings = metcap.parse_cards(CARD)
    assert listings[0] == {
        "id": "1005-jervis-street-vancouver-bc-v6e-3t1",
        "name": "The Summit",
        "permalink": "https://www.metcap.com/property/1005-jervis-street-vancouver-bc-v6e-3t1",
        "address": {"address": "1005 Jervis Street", "city": "Vancouver", "lat": 49.2849601, "lon": -123.1322621},
        "client": {"name": "MetCap Living"},
    }
    assert listings[1]["name"] is None
    assert listings[1]["address"]["address"] == "1265 Cardero Street"


def test_a_page_without_cards_fails_loudly():
    with pytest.raises(RuntimeError):
        metcap.parse_cards("<html></html>")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_fetch_metcap_listings.py -v`
Expected: FAIL with `FileNotFoundError` for `scripts/fetch_metcap_listings.py`.

- [ ] **Step 3: Write the scraper**

Create `scripts/fetch_metcap_listings.py`:

```python
"""Snapshot MetCap Living's Vancouver portfolio for raw_manager_listings.

MetCap Living manages rental buildings for their owners, so its listings
name the building's manager, not its owner.

Source: https://www.metcap.com/province-search-results?lang=en&province=117&city=Vancouver
renders every Vancouver property as a server-side card on one page (23 as of
2026-09-30):

    <div class="province-results__item" ... onclick="centerMap($(this), {lat: 49.28, lon: -123.13})">
      <h2><a href="/property/1005-jervis-street-vancouver-bc-v6e-3t1">1005 Jervis Street, Vancouver, BC V6E 3T1</a></h2>
      <p><span class="d-block">The Summit</span> ...

Writes data/raw/property_managers/metcap/<YYYY-MM-DD>.json in the same
shape as the theliftsystem.com feed (id, name, permalink, address, client),
so tc_core/ingest/manager_listings.py reads it unchanged. Cards carry no
staff contact details. Manual pull, like fetch_dorset_listings.py: re-run by
hand, then rebuild.
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

BASE_URL = "https://www.metcap.com"
SOURCE_URL = f"{BASE_URL}/province-search-results?lang=en&province=117&city=Vancouver"
MANAGER = "MetCap Living"
DEFAULT_DIR = "data/raw/property_managers/metcap"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

_CARD_RE = re.compile(
    r'<div class="province-results__item"[^>]*centerMap\(\$\(this\), \{lat: ([-\d.]+), lon: ([-\d.]+)\}\)'
)
_TITLE_RE = re.compile(r'<h2><a href="(/property/[^"]+)">(.*?)</a></h2>', re.DOTALL)
_NAME_RE = re.compile(r'<span class="d-block">([^<]*?)</span>', re.DOTALL)


def fetch_html(url: str = SOURCE_URL) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_cards(page: str) -> list[dict]:
    starts = list(_CARD_RE.finditer(page))
    if not starts:
        raise RuntimeError(
            "No province-results__item cards found: MetCap's page markup may "
            "have changed; re-check the source before assuming an empty result."
        )
    listings = []
    for i, start in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(page)
        card = page[start.start():end]
        title = _TITLE_RE.search(card)
        if not title:
            raise RuntimeError(f"Card {i + 1} has no property link.")
        full = htmllib.unescape(re.sub(r"<[^>]+>", "", title.group(2))).strip()
        # "1005 Jervis Street, Vancouver, BC V6E 3T1": the street, then the city.
        parts = [p.strip() for p in full.split(",")]
        # The name is a plain span in the card's own <p>; the last card's chunk
        # runs to the end of the page, so never search past that </p>.
        p_end = card.find("</p>", title.end())
        name = _NAME_RE.search(card, title.end(), p_end if p_end != -1 else len(card))
        listings.append({
            "id": title.group(1).rsplit("/", 1)[-1],
            "name": (htmllib.unescape(name.group(1)).strip() or None) if name else None,
            "permalink": BASE_URL + title.group(1),
            "address": {
                "address": parts[0],
                "city": parts[1] if len(parts) > 1 else None,
                "lat": float(start.group(1)),
                "lon": float(start.group(2)),
            },
            "client": {"name": MANAGER},
        })
    return listings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", default=DEFAULT_DIR, help="Snapshot directory")
    parser.add_argument("--date", default=date.today().isoformat(), help="Snapshot date (file name)")
    parser.add_argument("--html-file", help="Parse this saved page instead of fetching")
    args = parser.parse_args()

    page = Path(args.html_file).read_text(encoding="utf-8") if args.html_file else fetch_html()
    listings = parse_cards(page)
    print(f"{len(listings)} properties.", file=sys.stderr)

    out = Path(args.out_dir) / f"{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(listings, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

`_NAME_RE` only matches a `d-block` span whose content has no tag, and only inside the
card's own `<p>`. So in the second card, whose only span holds an `<a>`, it finds no name,
even though page text follows the last card.

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_fetch_metcap_listings.py -v`
Expected: PASS.

- [ ] **Step 5: Take the snapshot**

Run: `uv run python scripts/fetch_metcap_listings.py --date 2026-09-30`
Expected: "23 properties." and "Wrote data/raw/property_managers/metcap/2026-09-30.json".
- If the count differs, open the page and compare before going on.
- Check that every entry's `address.city` is "Vancouver".

- [ ] **Step 6: Update the manifest**

In `data/raw/property_managers/MANIFEST.md`, add a row for MetCap. Follow the format of the
Dorset and Wall rows. It needs:
- the source URL;
- the script `scripts/fetch_metcap_listings.py`;
- "manager (manages for owners), in property_managers.toml";
- 23 Vancouver properties on 2026-09-30.

- [ ] **Step 7: Checkpoint.** Report to the user; don't commit.

---

### Task 8: Curated managers, rebuild and review

**Files:**
- Modify: `data/curated/property_managers.toml` (gitignored)
- Modify: `docs/DATA_SOURCES.md` (property-manager listings entry)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Update `property_managers.toml`**

Replace the header comment and entries with:

```toml
# Property-management companies. A City rental licence held by one of these
# names the building's manager, not its landlord, and so does the company's
# own current listing (tc_core export: apply_property_managers).
# listing_names: what the company's listing feed calls it, when that differs.
# Hand-curated; not in git — keep your own copy.

[[manager]]
name = "Tribe Rental Management"
listing_names = ["Tribe Rentals"]
# 2026-09-24: holds licences for buildings the registry shows owned by
# Greenbrier Holdings and Shapiro Holdings; lists 25 Vancouver properties on
# its own site (theliftsystem.com client 118).

[[manager]]
name = "Dorset Realty Group"
# 2026-09-30: lists 32 Vancouver buildings at dorsetrealty.com/properties/residential/
# (scripts/fetch_dorset_listings.py); founded by Ron Schuss.

[[manager]]
name = "MetCap Living"
# 2026-09-30: lists 23 Vancouver buildings (scripts/fetch_metcap_listings.py);
# manages for owners, holds no Vancouver rental licence.
```

- [ ] **Step 2: Rebuild**

Run: `uv run python scripts/rebuild_data.py`
Expected:
- The ingest completes, then the "N building(s) added from landlord listings" block appears.
- It names at least: 1120 pacific st (Wall), 1050 burrard st, 2223 w broadway,
  455 abbott st, and 685 great northern way (Dorset).
- It can also name MetCap buildings that no City source lists.
- No Hornby & Drake (in development), no UBC/UEL addresses and no St. George's
  (North Vancouver): none of these has a City address point.

If an added address isn't rental housing, stop and tell the user. Don't build an exclusion
mechanism.

- [ ] **Step 3: Check the artifact**

Run this:

```bash
uv run python - <<'EOF'
import json
d = json.load(open("data/derived/artifacts/building_records.json"))
cols = d["columns"]; recs = d["records"]
recs = recs.values() if isinstance(recs, dict) else recs
rows = [dict(zip(cols, r)) if isinstance(r, list) else r for r in recs]
from collections import Counter
print(Counter((r["managed_by"], r["managed_by_source"]) for r in rows if r["managed_by"]))
print(sum(1 for r in rows if r["listings"]), "buildings with listings")
for r in rows:
    if r["building_source"] == "manager listing":
        print(r["address"], r["units"], [l["by"] for l in r["listings"]], r["owner_name"])
EOF
```

Expected:
- Tribe Rental Management appears with both `licence` and `listing`.
- Dorset Realty Group and MetCap Living appear with `listing`.
- Wall Financial Corporation never appears as a manager.
- Each listing-added building shows its lister.
- The owner is "(Unknown)" unless a registry filing reaches it. Whitehouse can show
  1136 Properties Ltd. through VAS267.

- [ ] **Step 4: Look at it in the map**

Run `cd frontend && npm run dev`. Then open the popups for:
- 1120 Pacific St: "Listed by Wall Financial Corporation ↗" and "Added from …".
- a Dorset building: "Managed by Dorset Realty Group ↗", with website provenance.
- a Tribe licence building: licence provenance, linked name.

Then pick "Dorset Realty Group" in the landlord search. The map should filter to its buildings.

- [ ] **Step 5: Document the source**

In `docs/DATA_SOURCES.md`, in the property-manager listings entry, add the following:
- The listed companies: Tribe (theliftsystem.com feed), Dorset, Wall and MetCap, with their scripts.
- How listings are used: names, the "Listed by" link, and `managed_by` for
  `property_managers.toml` companies.
- How listings can add a building: one that no City source lists, at an exact City
  address point, not unbuilt, from the latest snapshot. It has building source
  "manager listing" and never an owner.

- [ ] **Step 6: Final checkpoint**

Run: `uv run pytest && (cd frontend && npm test && npm run typecheck)`
Expected: everything PASSES.

Report to the user:
- the added-building list;
- the manager counts;
- that nothing is committed;
- the remaining data step (claim rows, below).

---

## After the plan: claim rows (research data, user-reviewed)

Not a code task. These are drafted with the user per spec section 4.
- **Dorset Realty / Schuss Family:**
  - `common_owner` between Dorset Properties Limited and each registry entity whose
    filing names Ronald Joseph Schuss;
  - a `network_label` claim, "Dorset Realty / Schuss Family".
- **Wall Financial:**
  - `common_owner` between Wall Financial Corporation and W.F.C. Properties (Pacific)
    Inc., 0888189 B.C. Ltd., 1111 Seymour Residence Ltd, W.F.C. Properties (Brunswick)
    and 1136 Properties Ltd.;
  - a `network_label` claim, "Wall Financial";
  - Wall & Redekop is excluded.
- **Process:** draft the rows into a scratch CSV for the user. The user sets `confirmed`
  and adds them to `data/curated/ownership_claims.csv`, then runs
  `uv run python scripts/update_claims.py`.
