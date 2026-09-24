# Unify Address Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the two competing address-normalization implementations (`tc_core.prepare.address` and `tc_core.normalize`) into the single `tc_core.normalize` implementation used everywhere, eliminating a demonstrated silent join failure between `buildings.addr_key` and `membership.addr_key`.

**Architecture:** `tc_core.normalize.normalize_street`/`addr_key_from_freeform` becomes the one canonical address-key function for the whole pipeline (`prepare/`, `ingest/`, `scripts/`). `tc_core.prepare.address` (`clean_address`, `fix_street_names`) is deleted; its three call sites (`prepare/properties.py`, `prepare/buildings.py`, `prepare/foi.py`) swap to `normalize.py` equivalents with no change to surrounding join/group-by structure. `ingest/overlays.py`'s private `_address_key_variants` (direction/range/unit-prefix candidate-key generation) is promoted into `normalize.py` as `address_key_variants`, since it's a general capability, not overlay-specific, and doing so removes the third divergent implementation.

**Tech Stack:** Python, polars (`prepare/`), pandas (`ingest/`), pytest, `uv run`.

**Spec:** This plan implements the recommendation from conversation analysis (no separate spec doc) — see the conversation's diagnosis: `clean_address` abbreviates `"way"` → `"w"` with no analogous rule in `normalize_street`, and `prepare/buildings.py` runs every building address through `clean_address` before `ingest/merge.py` re-runs it through `addr_key_from_freeform`, while `ingest/membership.py` computes member addr_keys through `addr_key_from_freeform` alone. Any building on a street type where the two normalizers disagree gets a `buildings.addr_key` that never matches the corresponding `membership.addr_key`, silently dropping that member's building attribution.

## Global Constraints

- No behavior change to any *matching/join structure* in `prepare/properties.py`, `prepare/buildings.py`, `prepare/foi.py` — only the normalizer function each call site invokes changes. Column names, join keys (`on=`, `group_by`, `unique(subset=...)`), and control flow stay exactly as they are today.
- `address_key_variants`'s promoted logic must be byte-for-byte the same algorithm as the current `ingest/overlays.py::_address_key_variants` — this is a relocation, not a rewrite. `_STREET_TYPE_RE`, `_loose_key`, `_build_loose_index`, `_match_key` stay in `overlays.py` (they're about loose-matching against a known-keys index, not canonical key generation).
- Per CLAUDE.md Section 6, address matching is verified by rebuilding and sanity-checking output on the real dataset, not by exhaustive new formal tests — Task 3 is that verification step and is required, not optional polish.
- Every existing test must still pass after each task (`uv run pytest tests/ -q`); baseline today is 74 passed.

## Review Focus

- A member's `primary_address1` on a street type only `clean_address` abbreviates (e.g. "Way" → "w") must now match its building's `addr_key` post-unification — this is the actual bug being fixed; Task 3 verifies it against real data rather than a synthetic test, per the Global Constraints note on this project's testing philosophy for address matching.
- `prepare/foi.py`'s 2023/2024 dedup-by-`_norm_address` must still collapse "100 Main Street" (2023) and "100 Main St" (2024) onto the same key after the swap — covered by the existing `test_prepare_foi.py::test_2024_wins_on_overlap_and_2023_fills_gaps`, re-run (not rewritten) in Task 2.
- `overlays.py`'s co-op/SRO matching (spelled-out directions, unit-prefix, civic-number ranges) must produce identical keys after the promotion — covered by re-running the existing `test_overlay_matching.py` suite unchanged in Task 1, since the algorithm isn't changing, only its location.
- `address_key_variants`'s own candidate-generation logic (direction folding, unit-prefix stripping, range collapsing) has no direct unit test today — Task 1 adds one so the promotion isn't a net loss of coverage.
- `prepare/properties.py::fix_street_names`→`move_trailing_direction` call site (property-tax-report `street_name` field) has no direct test today beyond end-to-end pipeline runs — Task 1 adds a unit test for the ported function so this narrow but real transformation (trailing-direction reordering) doesn't silently break.

---

## Task 1: Promote `address_key_variants`/`move_trailing_direction` into `normalize.py`, rewire `overlays.py`

**Files:**
- Modify: `src/tc_core/normalize.py`
- Modify: `src/tc_core/ingest/overlays.py:44-55,120-169`
- Create: `tests/test_normalize.py`

**Interfaces:**
- Produces: `normalize.address_key_variants(street: str) -> list[str]`, `normalize.move_trailing_direction(street_name: str | None) -> str | None` — both consumed by Task 2 (`move_trailing_direction` replaces `prepare.address.fix_street_names`) and by `overlays.py` in this task.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_normalize.py`:

```python
from tc_core.normalize import (
    addr_key_from_freeform,
    address_key_variants,
    clean_owner_label,
    move_trailing_direction,
    normalize_street,
)


def test_normalize_street_does_not_match_inside_a_longer_word():
    # normalize_street must not turn "Streetcar" into "Stcar" the way a bare
    # substring .replace(" street", " st") would.
    assert normalize_street("Main Streetcar") == "main streetcar"


def test_normalize_street_abbreviates_known_types():
    assert normalize_street("Burrard Street") == "burrard st"
    assert normalize_street("Pine Road") == "pine rd"
    assert normalize_street("Cambie Boulevard") == "cambie blvd"


def test_addr_key_from_freeform_extracts_civic_number():
    assert addr_key_from_freeform("1234 Burrard Street") == "1234 burrard st"


def test_move_trailing_direction_moves_direction_to_front():
    assert move_trailing_direction("Georgia W") == "w georgia"


def test_move_trailing_direction_passes_through_when_no_trailing_direction():
    assert move_trailing_direction("Main St") == "Main St"


def test_move_trailing_direction_passes_none_through():
    assert move_trailing_direction(None) is None


def test_address_key_variants_folds_spelled_out_direction():
    assert address_key_variants("1865 East 10th Avenue") == ["1865 e 10th ave"]


def test_address_key_variants_strips_unit_prefix_as_a_second_candidate():
    assert address_key_variants("#800 - 1047 Barclay St") == [
        "#800 - 1047 barclay st",
        "1047 barclay st",
    ]


def test_address_key_variants_collapses_a_civic_number_range():
    # "7401 - 7469 Talon Square" matches both the unit-prefix shape (\w+ "-"
    # \d+...) and the range shape (\d+ "-" \d+...), so all three candidates
    # come back, most-literal-first; _match_key in overlays.py tries each in
    # turn and returns the first that hits a known building key.
    assert address_key_variants("7401 - 7469 Talon Square") == [
        "7401 - 7469 talon square",
        "7469 talon square",
        "7401 talon square",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_normalize.py -v`
Expected: FAIL — `ImportError: cannot import name 'address_key_variants' from 'tc_core.normalize'` (and `move_trailing_direction`), since neither exists yet.

- [ ] **Step 3: Add the two functions to `normalize.py`**

Append to `src/tc_core/normalize.py` (after `addr_key_from_freeform`, before `parse_lat_lon`):

```python
_DIRECTIONS = {"e", "w", "n", "nw", "ne", "s", "sw", "se"}


def move_trailing_direction(street_name: str | None) -> str | None:
    """'Georgia W' -> 'w georgia': moves a trailing direction abbreviation
    (as used in the City's property-tax-report `street_name` field) to the
    front, matching the leading-direction convention used elsewhere.
    Passes the input through unchanged if it doesn't end in one."""
    if street_name is None:
        return None
    parts = street_name.lower().split(" ")
    if parts and parts[-1] in _DIRECTIONS:
        return " ".join(parts[-1:] + parts[:-1])
    return street_name


_DIRECTION_RE = re.compile(r"^(\d+)\s+(east|west|north|south)\b")
_DIRECTION_ABBR = {"east": "e", "west": "w", "north": "n", "south": "s"}
# "#800 - 1047 Barclay St", "100-2950 Heather St": a unit number in front of
# the civic number, not a civic-number range like "2165-2195 W 45th Av".
_UNIT_PREFIX_RE = re.compile(r"^#?\s*\w+\s*-\s*(\d+\s.+)$")
# "7401 - 7469 Talon Square", "500 & 502 Alexander St": a range of civic
# numbers; keyed by the first.
_RANGE_RE = re.compile(r"^(\d+)\s*(?:-|&|and)\s*\d+\s+(.+)$")


def address_key_variants(street: str) -> list[str]:
    """Candidate addr_keys for a source address, most literal first.

    addr_key_from_freeform takes exactly one leading civic number and one
    street string, so it can't handle spelled-out directions ("1865 East
    10th Avenue" vs the abbreviated "1865 e 10th ave" convention buildings
    are keyed with), a unit-number prefix ("#800 - 1047 Barclay St"), or a
    civic-number range ("7401 - 7469 Talon Square") on its own. This
    generates every variant worth trying against a known-keys index, most
    literal first; callers pick the first hit.
    """
    base = re.sub(r"\s+", " ", str(street)).strip().lower().rstrip("*").strip()
    raw = [base]
    m = _UNIT_PREFIX_RE.match(base)
    if m:
        raw.append(m.group(1))
    m = _RANGE_RE.match(base)
    if m:
        raw.append(f"{m.group(1)} {m.group(2)}")
    keys: list[str] = []
    for text in raw:
        text = _DIRECTION_RE.sub(lambda d: f"{d.group(1)} {_DIRECTION_ABBR[d.group(2)]}", text)
        key = addr_key_from_freeform(text)
        if key not in keys:
            keys.append(key)
    return keys
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_normalize.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Rewire `overlays.py` to the promoted functions and delete its local copies**

In `src/tc_core/ingest/overlays.py`:

Replace the import block (line 55):
```python
from ..normalize import addr_key_from_freeform
```
with:
```python
from ..normalize import addr_key_from_freeform, address_key_variants
```

Delete lines 120-128 (the now-duplicated `_DIRECTION_RE`, `_DIRECTION_ABBR`, `_UNIT_PREFIX_RE`, `_RANGE_RE` definitions), keeping `_STREET_TYPE_RE` (line 129) where it is.

Find the `_address_key_variants` function (originally lines 146-169) and delete its body, replacing every call site `_address_key_variants(...)` in the file (inside `_match_key`, see original line 184) with `address_key_variants(...)` from the import. Delete the now-empty local function definition entirely.

- [ ] **Step 6: Run the full test suite to confirm no regression**

Run: `uv run pytest tests/ -q`
Expected: `83 passed` (74 baseline + 9 new in `test_normalize.py`), including `tests/test_overlay_matching.py` and `tests/test_overlay_sources.py` unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/tc_core/normalize.py src/tc_core/ingest/overlays.py tests/test_normalize.py
git commit -m "Promote address_key_variants/move_trailing_direction into normalize.py"
```

---

## Task 2: Retire `prepare/address.py`, swap call sites in `properties.py`/`buildings.py`/`foi.py`

**Files:**
- Delete: `src/tc_core/prepare/address.py`
- Delete: `tests/test_prepare_address.py`
- Modify: `src/tc_core/prepare/properties.py:23,41,52,72,103,125,130`
- Modify: `src/tc_core/prepare/buildings.py:21,41`

**Interfaces:**
- Consumes: `normalize.addr_key_from_freeform(s: str) -> str`, `normalize.move_trailing_direction(s: str | None) -> str | None` (from Task 1).

- [ ] **Step 1: Swap `prepare/properties.py`**

Change the import (line 23):
```python
from .address import clean_address, fix_street_names
```
to:
```python
from ..normalize import addr_key_from_freeform, move_trailing_direction
```

Replace every `clean_address` reference with `addr_key_from_freeform` (lines 41, 52, 72, 103, 130 — five call sites, e.g. line 41 `).map_elements(clean_address, return_dtype=pl.Utf8),` becomes `).map_elements(addr_key_from_freeform, return_dtype=pl.Utf8),`, and identically for the other four).

Replace the one `fix_street_names` reference (line 125):
```python
pl.col("street_name").map_elements(fix_street_names, return_dtype=pl.Utf8),
```
with:
```python
pl.col("street_name").map_elements(move_trailing_direction, return_dtype=pl.Utf8),
```

- [ ] **Step 2: Swap `prepare/buildings.py`**

Change the import (line 21):
```python
from .address import clean_address
```
to:
```python
from ..normalize import addr_key_from_freeform
```

Update the `CLEAN` lambda (line 41):
```python
CLEAN = lambda col: pl.col(col).map_elements(clean_address, return_dtype=pl.Utf8)
```
to:
```python
CLEAN = lambda col: pl.col(col).map_elements(addr_key_from_freeform, return_dtype=pl.Utf8)
```
This lambda is reused at every `CLEAN(...)` call site in the file (line 70) and every direct `clean_address` reference (lines 77, 127, 154) — replace those three direct references with `addr_key_from_freeform` too, matching the pattern already used for `CLEAN`.

- [ ] **Step 3: Swap `prepare/foi.py`**

Change the import (line 17):
```python
from .address import clean_address
```
to:
```python
from ..normalize import addr_key_from_freeform
```

Replace both `clean_address` references (lines 35, 48) with `addr_key_from_freeform`.

- [ ] **Step 4: Delete the retired module and its test**

```bash
rm src/tc_core/prepare/address.py tests/test_prepare_address.py
```

- [ ] **Step 5: Run the full test suite to confirm no regression**

Run: `uv run pytest tests/ -q`
Expected: `80 passed` (83 from end of Task 1, minus the 3 deleted `test_prepare_address.py` tests). Pay particular attention to `tests/test_prepare_foi.py::test_2024_wins_on_overlap_and_2023_fills_gaps` — it depends on `"100 Main Street"` (2023) and `"100 Main St"` (2024) still colliding on the same `_norm_address` key post-swap; `normalize_street` folds `"street"` → `"st"` via a word-boundary rule, so this holds, but confirm the pass rather than assuming it.

- [ ] **Step 6: Commit**

```bash
git add -u src/tc_core/prepare tests/test_prepare_address.py
git commit -m "Retire prepare/address.py, unify on normalize.py's addr_key_from_freeform"
```

---

## Task 3: Rebuild derived data and verify the membership/building join fix

**Files:**
- None modified — this is a verification pass against real local data (`data/raw/`, `data/derived/`), per CLAUDE.md Section 6's stated testing approach for address-matching logic (sanity-checked against the real dataset, not exhaustive formal tests).

**Interfaces:**
- Consumes: the full pipeline via `scripts/rebuild_data.py`, the same entrypoint used for every other rebuild.

- [ ] **Step 1: Capture the pre-change baseline**

Before this task, `git stash` is not applicable (Tasks 1-2 are already committed) — instead capture the *current* (post-fix) derived output first, then diff against a fresh clone/checkout of the commit before Task 1 if a true before/after is wanted. Simpler and sufficient: since the bug is specifically about `buildings.addr_key` values for streets whose type-word `clean_address` and `normalize_street` abbreviate differently, directly inspect for that pattern:

```bash
uv run python scripts/rebuild_data.py
```

- [ ] **Step 2: Confirm addr_keys for "Way" streets no longer carry the old double-abbreviated form**

```bash
sqlite3 data/derived/*.db "SELECT address, addr_key FROM buildings WHERE address LIKE '% way' OR addr_key LIKE '%way%' LIMIT 20;" 2>/dev/null || \
uv run python -c "
import sqlite3, glob
conn = sqlite3.connect(glob.glob('data/derived/*.db')[0])
rows = conn.execute(\"SELECT address, addr_key FROM buildings WHERE addr_key LIKE '%way%' OR addr_key LIKE '% w' LIMIT 20\").fetchall()
for r in rows: print(r)
"
```
Expected: every `addr_key` for a "Way" street ends in `... way` (matching `normalize_street`'s form), not `... w`. If there are zero "Way" streets in the current dataset, note that explicitly rather than treating an empty result as a pass — re-run this check with a street-type word that *is* present in the data if "way" doesn't occur (check with `SELECT DISTINCT address FROM raw_buildings WHERE address LIKE '%way%'` first).

- [ ] **Step 3: Confirm the membership-to-building join rate**

```bash
uv run python -c "
import sqlite3, glob
conn = sqlite3.connect(glob.glob('data/derived/*.db')[0])
total = conn.execute('SELECT COUNT(*) FROM vtu_membership').fetchone()[0]
matched = conn.execute('SELECT COUNT(*) FROM vtu_membership WHERE building_id IS NOT NULL').fetchone()[0]
print(f'{matched}/{total} members matched to a building')
"
```
Record this number. Compare it against the same query run on `main` before this branch's changes (checkout `main` in a scratch worktree, rebuild, run the same query, return to this branch) — the post-fix count should be greater than or equal to the pre-fix count, never lower. An increase confirms the fix; an equal count means no member in the current dataset happened to live on a divergently-normalized street (still correct, just not a visible improvement on this dataset).

- [ ] **Step 4: Eyeball a sample of `buildings.csv` addresses for sane output**

```bash
uv run python -c "
import polars as pl
df = pl.read_csv('data/derived/buildings.csv')
print(df.select('address', 'primary_address', 'secondary_addresses').sample(20, seed=1))
"
```
Confirm addresses still look like sane street addresses (no fused civic-number ranges, no mid-word corruption) — this is the "sanity-check by eyeballing" CLAUDE.md calls for on this category of logic.

- [ ] **Step 5: Run the full test suite one final time**

Run: `uv run pytest tests/ -q`
Expected: `80 passed`.

- [ ] **Step 6: Commit the rebuilt derived artifacts if any are tracked**

`data/` is gitignored except the README and per-source manifests (per CLAUDE.md Section 3), so this step is likely a no-op — confirm with `git status` before assuming anything needs staging. If `datasette.yaml` or another tracked config references a derived-data path affected by this rebuild, review it, but do not commit regenerated data files themselves.
