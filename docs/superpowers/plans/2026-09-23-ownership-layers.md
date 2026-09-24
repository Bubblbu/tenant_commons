# Ownership Layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop flattening ownership into one label. Each building shows its own owner (LOTR reporting body, else business-licence holder) and, separately, its landlord network. Every ownership line gets a provenance indicator.

**Architecture:** The backend works out two layers per building. `metrics/registry_owners.py` (new) supplies the owner. `metrics/portfolios.py` supplies the network, and now also handles label claims, evidence counts and deterministic assignment of contested buildings. `export.py` publishes both through the explicit public column list. On the frontend, the popup renders owner, licence and network lines with CSS tooltips. The Buildings tab shows Owner and Network columns. The Landlords tab gets an Owners | Networks toggle, backed by a second marker index in `wiring.js`.

**Tech Stack:** Python 3.12 (pandas, polars, sqlite3, pytest via `uv`); TypeScript + vanilla JS (Vite, Leaflet, vitest in a node environment with no DOM).

**Spec:** `docs/superpowers/specs/2026-09-23-ownership-layers-design.md`

## Global Constraints

- `export.BUILDING_RECORD_COLUMNS` is the only gate on what reaches `building_records.json`. `ownership_claims.source_note` must never reach any artifact.
- Public provenance uses source types only. `public_registry` counts as `registry`; every other `source_type` collapses to `vtu_research`.
- Internal names stay `Portfolio` / `build_landlord_portfolios`. Public export fields are named `network_*` and `owner_*` exactly as listed in Task 5.
- Test baselines before Task 1: `uv run pytest tests/ -q` gives 81 passed, and `cd frontend && npx vitest run` gives 62 passed. Every task ends with both suites green. Frontend tasks also require `npx tsc --noEmit -p .` and `npx vite build` to pass.
- Frontend unit tests run with no DOM. New testable modules take plain objects and are tested with `EventTarget` fakes, as `search-clear.test.ts` does.
- Commits: plain messages, no Claude attribution. Never stage anything under `data/`, and never stage `datasette.yaml`.

### Plan-level corrections to the spec (rulings made while planning)

1. **`registry_filed` becomes `registry_retrieved`.** `raw_lotr_ownership.order_created_date` records when the Samwise order was placed (e.g. `2026-05-28 16:10:39.862`), not a registry filing date. The field name and the tooltip ("record retrieved …") say what the date actually is. Task 10 updates the spec to match.
2. **Registry owners live in a new `metrics/registry_owners.py`,** not inside `portfolios.py`. This keeps each file focused. The new module reuses `portfolios.py`'s PID helpers.
3. **Unknown owners get no source.** `owner_source` and `network_source` are `null` rather than `"licence"` when the key is `"unknown"`, and `network_buildings_on_map` is `null` for the `"unknown"` network. Without this, overlay rows and buildings with no licence would get a licence icon and an "(Unknown) network" line.
4. **"Same name" comparisons ignore case and punctuation.** The popup's licence line and the Buildings tab's Network cell both use a shared `sameName()` helper, so "GLR PROPERTIES LTD." and "Glr Properties Ltd" count as the same name.

## Review Focus

1. **Unknown or overlay records:** a building or overlay with no known owner must show "(Unknown)" with no provenance icon and no network line. Pinned by Task 5 (`test_unknown_owners_carry_no_source_and_no_network_size`) and Task 7 (`shows no provenance for an unknown owner`).
2. **Owner and licence names that differ only in formatting:** no redundant "Licensed as" line, and a blank Network cell. Pinned by Task 7 (`skips the licence line…`) and Task 8 (`leaves the network cell blank…`).
3. **A building whose PIDs reach two networks:** the same network must win whatever order the claims were inserted in. Pinned by Task 2 (both contested tests run with both insertion orders).
4. **Manual claim notes that could identify a tenant:** these must never appear in any artifact. Pinned by Task 5 (`test_claim_source_notes_never_reach_any_artifact`), which scans every output file for a canary string.
5. **A network label that looks like an entity name:** it must never merge into the entity list or change the network's key. Pinned by Task 1 (the verbatim, not-an-entity and importer tests) and Task 2/Task 5 (the label renames but the key is unchanged).

---

### Task 1: `network_label` claims

**Files:**
- Modify: `src/tc_core/claims.py`
- Modify: `src/tc_core/ingest/ownership_claims.py`
- Test: `tests/test_claims_network_labels.py` (create)

**Interfaces:**
- Produces:
  - `claims.NETWORK_LABEL = "network_label"`
  - `claims.network_label_claims(conn) -> dict[str, tuple[str, str, int]]`, mapping `sanitize_owner(entity_a)` to `(label, updated_at, claim_id)` for the latest confirmed, active label claim per entity
  - `claims.confirmed_common_owner_edges(conn) -> list[tuple[str, str, str]]`, returning `(entity_a, entity_b, source_type)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_claims_network_labels.py`:

```python
"""network_label claims: display names for landlord networks (spec
2026-09-23-ownership-layers-design.md §4). The label is free text, never an
entity, so it must not collapse onto entity spellings or appear as one."""

from __future__ import annotations

import logging

import pandas as pd

from tc_core.claims import (
    NETWORK_LABEL,
    confirmed_common_owner_edges,
    find_similar_entity,
    list_known_entities,
    network_label_claims,
    record_claim,
)
from tc_core.db import get_connection, init_db
from tc_core.ingest.ownership_claims import ingest_ownership_claims


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def test_network_label_text_is_stored_verbatim_apart_from_whitespace():
    conn = _conn()
    record_claim(conn, "GLR PROPERTIES LTD.", "  GLR Properties /  Rener family ",
                 NETWORK_LABEL, "manual_research", confidence="confirmed")
    assert conn.execute("SELECT entity_b FROM ownership_claims").fetchone()[0] == (
        "GLR Properties / Rener family"
    )


def test_label_resembling_an_entity_is_not_collapsed_onto_it():
    conn = _conn()
    record_claim(conn, "GLR PROPERTIES LTD.", "RENER, GEORGE", "common_owner",
                 "public_registry", confidence="confirmed")
    record_claim(conn, "RENER, GEORGE", "Glr Properties Ltd", NETWORK_LABEL,
                 "manual_research", confidence="confirmed")
    label = conn.execute(
        "SELECT entity_b FROM ownership_claims WHERE relationship = ?", (NETWORK_LABEL,)
    ).fetchone()[0]
    assert label == "Glr Properties Ltd"


def test_labels_are_not_known_entities():
    conn = _conn()
    record_claim(conn, "GLR PROPERTIES LTD.", "GLR network", NETWORK_LABEL,
                 "manual_research", confidence="confirmed")
    assert list_known_entities(conn) == ["GLR PROPERTIES LTD."]
    assert find_similar_entity(conn, "glr network") is None


def test_network_label_claims_keep_the_latest_confirmed_active_label():
    conn = _conn()
    record_claim(conn, "A LTD", "Old name", NETWORK_LABEL, "manual_research",
                 confidence="confirmed", claim_key="l1")
    record_claim(conn, "A LTD", "New name", NETWORK_LABEL, "manual_research",
                 confidence="confirmed", claim_key="l2")
    record_claim(conn, "B LTD", "Unconfirmed", NETWORK_LABEL, "manual_research", claim_key="l3")
    record_claim(conn, "C LTD", "Retracted", NETWORK_LABEL, "manual_research",
                 confidence="confirmed", status="retracted", claim_key="l4")
    labels = network_label_claims(conn)
    assert {key: value[0] for key, value in labels.items()} == {"a-ltd": "New name"}


def test_confirmed_common_owner_edges_carry_their_source_type():
    conn = _conn()
    record_claim(conn, "A LTD", "B LTD", "common_owner", "public_registry", confidence="confirmed")
    record_claim(conn, "A LTD", "C LTD", "common_owner", "tenant_report", confidence="confirmed")
    record_claim(conn, "A LTD", "D LTD", "common_owner", "manual_research")
    record_claim(conn, "A LTD", "Label", NETWORK_LABEL, "manual_research", confidence="confirmed")
    assert sorted(confirmed_common_owner_edges(conn)) == [
        ("A LTD", "B LTD", "public_registry"),
        ("A LTD", "C LTD", "tenant_report"),
    ]


def test_bulk_import_does_not_report_a_label_as_a_collapsed_entity(tmp_path, caplog):
    conn = _conn()
    record_claim(conn, "GLR PROPERTIES LTD.", "RENER, GEORGE", "common_owner",
                 "public_registry", confidence="confirmed")
    csv = tmp_path / "claims.csv"
    pd.DataFrame([{
        "claim_key": "label-1", "entity_a": "RENER, GEORGE", "entity_b": "Glr Properties Ltd",
        "relationship": NETWORK_LABEL, "source_type": "manual_research", "confidence": "confirmed",
    }]).to_csv(csv, index=False)
    caplog.set_level(logging.INFO, logger="tc_core.ingest")

    ingest_ownership_claims(conn, str(csv))

    assert "Glr Properties Ltd" not in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_claims_network_labels.py -v`
Expected: collection error `ImportError: cannot import name 'NETWORK_LABEL' from 'tc_core.claims'`.

- [ ] **Step 3: Implement in `claims.py`**

In `src/tc_core/claims.py`, add below `_CLAIM_FIELDS`:

```python
# Names a landlord network: entity_a is any entity in a common_owner cluster,
# entity_b is display text (never an entity — see record_claim()).
NETWORK_LABEL = "network_label"
```

In `record_claim()`, replace:

```python
    entity_a = _resolve_entity_label(conn, entity_a)
    entity_b = _resolve_entity_label(conn, entity_b)
```

with:

```python
    entity_a = _resolve_entity_label(conn, entity_a)
    if relationship == NETWORK_LABEL:
        entity_b = " ".join(str(entity_b).split())
    else:
        entity_b = _resolve_entity_label(conn, entity_b)
```

In `list_known_entities()`, replace the query with:

```python
    rows = conn.execute(
        "SELECT entity_a AS entity FROM ownership_claims "
        "UNION SELECT entity_b FROM ownership_claims WHERE relationship != ? "
        "ORDER BY 1",
        (NETWORK_LABEL,),
    ).fetchall()
```

Append at the end of the file:

```python
def network_label_claims(conn: sqlite3.Connection) -> dict[str, tuple[str, str, int]]:
    """sanitize_owner(entity) -> (label, updated_at, claim_id) of the latest
    confirmed, active network_label claim naming that entity."""
    rows = conn.execute(
        "SELECT entity_a, entity_b, updated_at, claim_id FROM ownership_claims "
        "WHERE relationship = ? AND status = 'active' AND confidence = 'confirmed' "
        "ORDER BY updated_at, claim_id",
        (NETWORK_LABEL,),
    ).fetchall()
    return {
        sanitize_owner(entity): (label, updated_at, claim_id)
        for entity, label, updated_at, claim_id in rows
    }


def confirmed_common_owner_edges(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """(entity_a, entity_b, source_type) of every confirmed, active common_owner claim."""
    rows = conn.execute(
        "SELECT entity_a, entity_b, source_type FROM ownership_claims "
        "WHERE relationship = 'common_owner' AND status = 'active' AND confidence = 'confirmed'"
    ).fetchall()
    return [(a, b, source_type) for a, b, source_type in rows]
```

- [ ] **Step 4: Skip the label in the bulk importer's similar-entity log**

In `src/tc_core/ingest/ownership_claims.py`:
- Add `NETWORK_LABEL` to the existing `from ..claims import …` line.
- In `ingest_ownership_claims()`, replace `for entity in (entity_a, entity_b):` with:

```python
        relationship = _cell(row, "relationship")
        # A network_label's entity_b is display text, not an entity.
        entities = (entity_a,) if relationship == NETWORK_LABEL else (entity_a, entity_b)
        for entity in entities:
```

- In the `record_claim(...)` call below it, replace `relationship=_cell(row, "relationship"),` with `relationship=relationship,`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_claims_network_labels.py -v`
Expected: 6 passed.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 87 passed.

- [ ] **Step 7: Commit**

```bash
git add src/tc_core/claims.py src/tc_core/ingest/ownership_claims.py tests/test_claims_network_labels.py
git commit -m "Add network_label claims for naming landlord networks"
```

---

### Task 2: Network names, evidence, and deterministic contested buildings

**Files:**
- Modify: `src/tc_core/metrics/portfolios.py`
- Test: `tests/test_portfolios.py`

**Interfaces:**
- Consumes: `claims.NETWORK_LABEL`, `claims.network_label_claims`, `claims.confirmed_common_owner_edges` (Task 1).
- Produces: `Portfolio` gains `name_source: str` (`"default"` or `"claim"`) and `evidence: dict[str, int]` (keys `"registry"`, `"vtu_research"`). `portfolio_key` is always `sanitize_owner(default name)`. `build_landlord_portfolios(conn, pid_address_map_path) -> dict[str, Portfolio]` keeps its signature. `_normalize_pid` and `_load_pid_to_addr_key` stay importable, because Task 3 imports them.

- [ ] **Step 1: Write the failing tests**

In `tests/test_portfolios.py`, change the claims import to:

```python
from tc_core.claims import NETWORK_LABEL, record_claim
```

and append:

```python
def _glr_setup(tmp_path):
    conn = _conn()
    _insert_raw_lotr(conn, "111", "GLR PROPERTIES LTD")
    _insert_raw_lotr(conn, "222", "GLR PROPERTIES LTD")
    _insert_raw_lotr(conn, "333", "RENER HOLDINGS LTD")
    pid_map_path = tmp_path / "pid_address_map.csv"
    _write_pid_address_map(
        pid_map_path,
        [("111", "1200 alberni st"), ("222", "1210 alberni st"), ("333", "800 nicola st")],
    )
    return conn, str(pid_map_path)


def _link(conn, a, b, source_type="public_registry", confidence="confirmed"):
    record_claim(conn, entity_a=a, entity_b=b, relationship="common_owner",
                 source_type=source_type, confidence=confidence)


def test_network_name_defaults_to_the_entity_with_most_pids(tmp_path):
    conn, pid_map = _glr_setup(tmp_path)
    _link(conn, "GLR PROPERTIES LTD", "RENER HOLDINGS LTD")
    p = build_landlord_portfolios(conn, pid_map)["800 nicola st"]
    assert (p.portfolio_name, p.name_source, p.portfolio_key) == (
        "GLR PROPERTIES LTD", "default", "glr-properties-ltd"
    )


def test_confirmed_network_label_renames_the_network_but_keeps_its_key(tmp_path):
    conn, pid_map = _glr_setup(tmp_path)
    _link(conn, "GLR PROPERTIES LTD", "RENER HOLDINGS LTD")
    record_claim(conn, "RENER HOLDINGS LTD", "Rener family", NETWORK_LABEL,
                 "manual_research", confidence="confirmed")
    p = build_landlord_portfolios(conn, pid_map)["1200 alberni st"]
    assert (p.portfolio_name, p.name_source, p.portfolio_key) == (
        "Rener family", "claim", "glr-properties-ltd"
    )


def test_unconfirmed_or_stray_labels_are_ignored(tmp_path):
    conn, pid_map = _glr_setup(tmp_path)
    _link(conn, "GLR PROPERTIES LTD", "RENER HOLDINGS LTD")
    record_claim(conn, "RENER HOLDINGS LTD", "Unconfirmed name", NETWORK_LABEL, "manual_research")
    record_claim(conn, "SOMEONE ELSE LTD", "Stray name", NETWORK_LABEL,
                 "manual_research", confidence="confirmed")
    p = build_landlord_portfolios(conn, pid_map)["1200 alberni st"]
    assert (p.portfolio_name, p.name_source) == ("GLR PROPERTIES LTD", "default")


def test_evidence_counts_collapse_non_registry_sources(tmp_path):
    conn, pid_map = _glr_setup(tmp_path)
    _link(conn, "GLR PROPERTIES LTD", "RENER HOLDINGS LTD")
    _link(conn, "GLR PROPERTIES LTD", "RENER, LUDVIK", source_type="manual_research")
    _link(conn, "RENER HOLDINGS LTD", "RENER, LUDVIK", source_type="tenant_report")
    _link(conn, "RENER HOLDINGS LTD", "RENER, ANA", source_type="manual_research",
          confidence="unconfirmed")
    p = build_landlord_portfolios(conn, pid_map)["1200 alberni st"]
    assert p.evidence == {"registry": 1, "vtu_research": 2}


def _contested(tmp_path, pids: list[tuple[str, str, str]], x_first: bool):
    """pids: (pid, reporting body, addr_key). Networks X and Y are each one
    confirmed link; x_first controls which claim is inserted first."""
    conn = _conn()
    for pid, body, _ in pids:
        _insert_raw_lotr(conn, pid, body)
    pid_map = tmp_path / f"map_{len(pids)}_{x_first}.csv"
    _write_pid_address_map(pid_map, [(pid, addr_key) for pid, _, addr_key in pids])
    links = [("X ONE LTD", "X TWO LTD"), ("Y ONE LTD", "Y TWO LTD")]
    for a, b in (links if x_first else links[::-1]):
        _link(conn, a, b)
    return build_landlord_portfolios(conn, str(pid_map))


def test_contested_building_goes_to_the_network_holding_most_of_its_pids(tmp_path):
    pids = [("1", "X ONE LTD", "5 shared st"), ("2", "X ONE LTD", "5 shared st"),
            ("3", "Y ONE LTD", "5 shared st"), ("4", "Y ONE LTD", "9 y st")]
    for x_first in (True, False):
        assert _contested(tmp_path, pids, x_first)["5 shared st"].portfolio_key == "x-one-ltd"


def test_contested_tie_goes_to_the_larger_network(tmp_path):
    pids = [("1", "X ONE LTD", "5 shared st"), ("3", "Y ONE LTD", "5 shared st"),
            ("4", "Y ONE LTD", "9 y st")]
    for x_first in (True, False):
        assert _contested(tmp_path, pids, x_first)["5 shared st"].portfolio_key == "y-one-ltd"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_portfolios.py -v`
Expected: the new naming and evidence tests fail with `AttributeError: 'Portfolio' object has no attribute 'name_source'` (and `evidence`). The label test fails on the name. At least one insertion order of each contested test fails, which proves the old last-writer-wins behaviour.

- [ ] **Step 3: Implement**

In `src/tc_core/metrics/portfolios.py`, replace everything from `@dataclass` through the end of the file (`Portfolio`, `_load_pid_to_addr_key`, `_entity_pids`, `build_landlord_portfolios`) with the code below. Keep the module docstring, `_normalize_pid`, and the imports. Extend the imports to:

```python
import csv
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from ..claims import confirmed_common_owner_edges, network_label_claims, resolve_owner_groups
from ..normalize import sanitize_owner

REGISTRY_SOURCE = "public_registry"
```

```python
@dataclass
class Portfolio:
    # Stable id: sanitize_owner() of the default name, whatever the display
    # name — relabelling a network through a claim never changes its key.
    portfolio_key: str
    # Display name: a confirmed network_label claim if any entity in the
    # cluster has one (latest wins), else the entity holding the most PIDs
    # (ties alphabetical).
    portfolio_name: str
    name_source: str  # "default" | "claim"
    entities: list[str]
    addr_keys: set[str] = field(default_factory=set)
    # Confirmed common_owner claims inside the cluster, by public source
    # category: "registry" (public_registry) or "vtu_research" (all others).
    evidence: dict[str, int] = field(default_factory=dict)


def _load_pid_to_addr_key(path: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid = _normalize_pid(row.get("pid") or "")
            addr_key = (row.get("addr_key") or "").strip()
            if pid and addr_key:
                mapping[pid] = addr_key
    return mapping


def _entity_pids(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """{sanitize_owner(reporting_body_name): {pid, ...}}.

    Keyed by sanitize_owner() rather than the verbatim string: raw_lotr_
    ownership is un-deduplicated source data, so the same corporation can
    appear as both "GLR PROPERTIES LTD" and "GLR PROPERTIES LTD." across rows,
    while ownership_claims stores only one of those spellings.
    """
    rows = conn.execute(
        "SELECT reporting_body_name, pid FROM raw_lotr_ownership "
        "WHERE reporting_body_name IS NOT NULL AND pid IS NOT NULL"
    ).fetchall()
    pids_by_entity: dict[str, set[str]] = {}
    for reporting_body_name, pid in rows:
        normalized_pid = _normalize_pid(pid)
        if not normalized_pid:
            continue
        pids_by_entity.setdefault(sanitize_owner(reporting_body_name), set()).add(normalized_pid)
    return pids_by_entity


def _clusters(conn: sqlite3.Connection) -> list[list[str]]:
    clusters: list[list[str]] = []
    seen: set[str] = set()
    for entity, others in resolve_owner_groups(conn).items():
        if entity in seen:
            continue
        cluster = {entity, *others}
        seen |= cluster
        clusters.append(sorted(cluster))
    return clusters


def build_landlord_portfolios(
    conn: sqlite3.Connection, pid_address_map_path: str
) -> dict[str, Portfolio]:
    """Returns {addr_key: Portfolio} for every building reached by a confirmed
    common_owner cluster. A cluster reaches an addr_key if any of its entities
    is the reporting body for a PID mapped to it. A building reached by
    several clusters goes to the one holding most of its PIDs, then the
    larger cluster (more addr_keys), then the smaller key — independent of
    claim order.
    """
    pid_to_addr_key = _load_pid_to_addr_key(pid_address_map_path)
    entity_pids = _entity_pids(conn)
    labels = network_label_claims(conn)
    clusters = _clusters(conn)

    cluster_of = {entity: i for i, cluster in enumerate(clusters) for entity in cluster}
    evidence = [{"registry": 0, "vtu_research": 0} for _ in clusters]
    for a, b, source_type in confirmed_common_owner_edges(conn):
        i = cluster_of.get(a)
        if i is not None and cluster_of.get(b) == i:
            evidence[i]["registry" if source_type == REGISTRY_SOURCE else "vtu_research"] += 1

    portfolios: list[Portfolio] = []
    portfolio_pids: list[set[str]] = []
    for i, cluster in enumerate(clusters):
        pids: set[str] = set()
        for entity in cluster:
            pids |= entity_pids.get(sanitize_owner(entity), set())
        addr_keys = {pid_to_addr_key[pid] for pid in pids if pid in pid_to_addr_key}
        if not addr_keys:
            continue
        default_name = max(cluster, key=lambda e: len(entity_pids.get(sanitize_owner(e), set())))
        label = max(
            (labels[key] for key in {sanitize_owner(e) for e in cluster} if key in labels),
            key=lambda claim: (claim[1], claim[2]),
            default=None,
        )
        portfolios.append(
            Portfolio(
                portfolio_key=sanitize_owner(default_name),
                portfolio_name=label[0] if label else default_name,
                name_source="claim" if label else "default",
                entities=cluster,
                addr_keys=addr_keys,
                evidence=evidence[i],
            )
        )
        portfolio_pids.append(pids)

    pid_counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for j, pids in enumerate(portfolio_pids):
        for pid in pids:
            addr_key = pid_to_addr_key.get(pid)
            if addr_key is not None:
                pid_counts[addr_key][j] += 1

    by_addr_key: dict[str, Portfolio] = {}
    for addr_key, per_portfolio in pid_counts.items():
        best = min(
            per_portfolio,
            key=lambda j: (-per_portfolio[j], -len(portfolios[j].addr_keys), portfolios[j].portfolio_key),
        )
        by_addr_key[addr_key] = portfolios[best]
    return by_addr_key
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_portfolios.py -v`
Expected: 10 passed (4 existing + 6 new).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 93 passed. `export.py` still reads `portfolio_name`, `addr_keys`, `entities` and `portfolio_key`, which all still exist.

- [ ] **Step 6: Commit**

```bash
git add src/tc_core/metrics/portfolios.py tests/test_portfolios.py
git commit -m "Name networks via label claims, count evidence, assign contested buildings deterministically"
```

---

### Task 3: Registered owners per building

**Files:**
- Create: `src/tc_core/metrics/registry_owners.py`
- Test: `tests/test_registry_owners.py` (create)

**Interfaces:**
- Consumes: `portfolios._load_pid_to_addr_key`, `portfolios._normalize_pid` (Task 2).
- Produces:
  - `RegistryOwnership(owners: list[str], pids: list[str], retrieved: str | None)`
  - `build_registry_owners(conn, pid_address_map_path) -> dict[str, RegistryOwnership]`, keyed by `addr_key`. `owners` is primary first. `pids` are as filed (dashed) and sorted. `retrieved` is `YYYY-MM-DD` or `None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_registry_owners.py`:

```python
"""Per-building registered owners from the BC Land Owner Transparency
Registry (spec 2026-09-23-ownership-layers-design.md §3)."""

from __future__ import annotations

from tc_core.db import get_connection, init_db
from tc_core.metrics.registry_owners import build_registry_owners


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def _lotr(conn, pid, name, created="2026-05-28 16:10:39.862", status="SUCCESS"):
    conn.execute(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, order_created_date, "
        "data_fetch_status, ingested_at) VALUES (?, ?, ?, ?, 'now')",
        (pid, name, created, status),
    )


def _pid_map(tmp_path, rows):
    path = tmp_path / "pid_address_map.csv"
    lines = ["pid,address_point_id,address,addr_key,local_area,lat_lon"]
    lines += [f'{pid},1,{key},{key},West End,"49.28,-123.13"' for pid, key in rows]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def test_primary_owner_holds_the_most_pids(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-001", "SMALL LTD")
    _lotr(conn, "001-000-002", "BIG LTD")
    _lotr(conn, "001-000-003", "BIG LTD")
    owners = build_registry_owners(conn, _pid_map(
        tmp_path, [("001000001", "1 a st"), ("001000002", "1 a st"), ("001000003", "1 a st")]))
    assert owners["1 a st"].owners == ["BIG LTD", "SMALL LTD"]


def test_equal_pid_counts_break_alphabetically(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-001", "ZED LTD")
    _lotr(conn, "001-000-002", "ALPHA LTD")
    owners = build_registry_owners(conn, _pid_map(
        tmp_path, [("001000001", "1 a st"), ("001000002", "1 a st")]))
    assert owners["1 a st"].owners == ["ALPHA LTD", "ZED LTD"]


def test_spelling_variants_are_one_owner_shown_by_the_commonest_spelling(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-001", "GLR PROPERTIES LTD.")
    _lotr(conn, "001-000-001", "GLR PROPERTIES LTD.")
    _lotr(conn, "001-000-002", "GLR PROPERTIES LTD")
    owners = build_registry_owners(conn, _pid_map(
        tmp_path, [("001000001", "1 a st"), ("001000002", "1 a st")]))
    assert owners["1 a st"].owners == ["GLR PROPERTIES LTD."]


def test_pids_as_filed_and_latest_retrieval_date(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-002", "A LTD", created="2026-05-28 16:10:39.862")
    _lotr(conn, "001-000-001", "A LTD", created="2026-08-19 16:23:53.762")
    owners = build_registry_owners(conn, _pid_map(
        tmp_path, [("001000001", "1 a st"), ("001000002", "1 a st")]))
    assert owners["1 a st"].pids == ["001-000-001", "001-000-002"]
    assert owners["1 a st"].retrieved == "2026-08-19"


def test_failed_fetches_and_unmapped_pids_are_ignored(tmp_path):
    conn = _conn()
    _lotr(conn, "001-000-001", "A LTD", status="FAILED")
    _lotr(conn, "009-999-999", "B LTD")
    owners = build_registry_owners(conn, _pid_map(tmp_path, [("001000001", "1 a st")]))
    assert owners == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry_owners.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'tc_core.metrics.registry_owners'`.

- [ ] **Step 3: Implement**

Create `src/tc_core/metrics/registry_owners.py`:

```python
"""Per-building registered owners from the BC Land Owner Transparency Registry.

A building's registered owners are the LOTR reporting bodies filed against
its PIDs (bridged to addr_key by pid_address_map.csv). The primary owner holds
the most of the building's PIDs, ties broken alphabetically. Spelling variants
of one body ("GLR PROPERTIES LTD" / "GLR PROPERTIES LTD.") count as one owner,
shown by its most frequent spelling.
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..normalize import sanitize_owner
from .portfolios import _load_pid_to_addr_key, _normalize_pid


@dataclass
class RegistryOwnership:
    owners: list[str]
    pids: list[str]
    # Date the registry record was retrieved (Samwise order date), not a filing date.
    retrieved: str | None


def build_registry_owners(
    conn: sqlite3.Connection, pid_address_map_path: str
) -> dict[str, RegistryOwnership]:
    pid_to_addr_key = _load_pid_to_addr_key(pid_address_map_path)
    rows = conn.execute(
        "SELECT pid, reporting_body_name, order_created_date FROM raw_lotr_ownership "
        "WHERE reporting_body_name IS NOT NULL AND pid IS NOT NULL "
        "AND (data_fetch_status IS NULL OR data_fetch_status = 'SUCCESS')"
    ).fetchall()

    body_pids: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    spellings: dict[str, Counter] = defaultdict(Counter)
    filed: dict[str, set[str]] = defaultdict(set)
    retrieved: dict[str, str] = {}
    for pid, name, created in rows:
        addr_key = pid_to_addr_key.get(_normalize_pid(pid))
        if addr_key is None:
            continue
        name = name.strip()
        body = sanitize_owner(name)
        body_pids[addr_key][body].add(_normalize_pid(pid))
        spellings[body][name] += 1
        filed[addr_key].add(pid.strip())
        if created:
            day = str(created).split(" ")[0].split("T")[0]
            if day > retrieved.get(addr_key, ""):
                retrieved[addr_key] = day

    def display(body: str) -> str:
        counts = spellings[body]
        top = max(counts.values())
        return min(name for name, count in counts.items() if count == top)

    result: dict[str, RegistryOwnership] = {}
    for addr_key, bodies in body_pids.items():
        ranked = sorted(bodies, key=lambda body: (-len(bodies[body]), display(body)))
        result[addr_key] = RegistryOwnership(
            owners=[display(body) for body in ranked],
            pids=sorted(filed[addr_key]),
            retrieved=retrieved.get(addr_key),
        )
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry_owners.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 98 passed.

- [ ] **Step 6: Commit**

```bash
git add src/tc_core/metrics/registry_owners.py tests/test_registry_owners.py
git commit -m "Derive each building's registered owners from LOTR filings"
```

---

### Task 4: Business-licence year through the pipeline

**Files:**
- Modify: `src/tc_core/prepare/buildings.py`
- Modify: `src/tc_core/ingest/raw_buildings.py`
- Modify: `src/tc_core/schema.sql`
- Test: `tests/test_raw_buildings_bsns_year.py` (create)

**Interfaces:**
- Produces: `raw_buildings.bsns_year INTEGER`, the four-digit licence data year, which is the same on every row. Task 5 reads `MAX(bsns_year)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_raw_buildings_bsns_year.py`:

```python
"""buildings.csv carries the business-licence data year (bsns_year) that the
export publishes as filter_config.licence_year."""

from tc_core.db import get_connection, init_db
from tc_core.ingest.raw_buildings import ingest_raw_buildings


def test_bsns_year_is_ingested(tmp_path):
    path = tmp_path / "buildings.csv"
    path.write_text("address,local_area,bsns_group,bsns_year\n100 main st,Downtown,X Ltd,2026\n")
    conn = get_connection(":memory:")
    init_db(conn)

    assert ingest_raw_buildings(conn, str(path)) == 1
    assert conn.execute("SELECT bsns_year FROM raw_buildings").fetchone()[0] == 2026
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_raw_buildings_bsns_year.py -v`
Expected: FAIL with `RuntimeError: buildings.csv has columns with no raw_buildings mapping: ['bsns_year']`.

- [ ] **Step 3: Implement**

In `src/tc_core/schema.sql`, inside `CREATE TABLE raw_buildings`, replace:

```sql
    bsns_subtype TEXT,
    value_land TEXT,
```

with:

```sql
    bsns_subtype TEXT,
    bsns_year INTEGER,      -- business-licence data year this build used; same on every row
    value_land TEXT,
```

In `src/tc_core/ingest/raw_buildings.py`, in `RAW_BUILDINGS_COLUMNS`, replace `"bsns_subtype",` with:

```python
    "bsns_subtype",
    "bsns_year",
```

In `src/tc_core/prepare/buildings.py`, replace:

```python
    latest_year = businesses.select(pl.col("folderyear").cast(pl.Int32).max()).item()
    print(f"Using latest business-licence folderyear: {latest_year}")
```

with:

```python
    latest_year = businesses.select(pl.col("folderyear").cast(pl.Int32).max()).item()
    print(f"Using latest business-licence folderyear: {latest_year}")
    # The City publishes folderyear as two digits ("26").
    licence_year = latest_year if latest_year >= 1000 else 2000 + latest_year
```

Then, directly above the final `buildings = buildings.select(` (the one ending in `.sort("units", …)`), add:

```python
    buildings = buildings.with_columns(bsns_year=pl.lit(licence_year))
```

and in that select list replace `"bsns_subtype",` with:

```python
        "bsns_subtype",
        "bsns_year",
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_raw_buildings_bsns_year.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 99 passed.

- [ ] **Step 6: Commit**

```bash
git add src/tc_core/prepare/buildings.py src/tc_core/ingest/raw_buildings.py src/tc_core/schema.sql tests/test_raw_buildings_bsns_year.py
git commit -m "Carry the business-licence data year into raw_buildings"
```

---

### Task 5: Export contract, with owner and network as separate layers

**Files:**
- Modify: `src/tc_core/export.py`
- Modify: `tests/test_export_artifacts.py`, `tests/test_export_source_discriminator.py`
- Regenerate: `frontend/fixtures/*` (via `scripts/make_frontend_fixtures.py`)
- Test: `tests/test_export_ownership.py` (create)

**Interfaces:**
- Consumes: `build_registry_owners` (Task 3), `build_landlord_portfolios` with `name_source`/`evidence` (Task 2), `raw_buildings.bsns_year` (Task 4).
- Produces, for every `building_records.json` record: `owner_name`, `owner_key`, `owner_source` (`"registry"`, `"licence"` or `null`), `registered_owners` (list), `registry_pids` (list), `registry_retrieved`, `licence_holder`, `network_key`, `network_name`, `network_source` (`"claims"`, `"licence"` or `null`), `network_name_source`, `network_entities`, `network_buildings_on_map` (int or `null`), `network_properties_on_title`, `network_evidence` (`{"registry", "vtu_research"}` or `null`). The old `owner_group` and `portfolio_*` fields are gone. `marker_metadata.json` markers gain `network_key`. `filter_config.json` gains `licence_year`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_export_ownership.py`:

```python
"""Owner vs. network in the export (spec 2026-09-23-ownership-layers-design.md)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tc_core.claims import NETWORK_LABEL, record_claim
from tc_core.db import init_db
from tc_core.export import export_artifacts

CANARY = "CANARY-7f3a tenant in unit 4 said so"


def _seed(conn, tmp_path: Path) -> str:
    conn.executemany(
        "INSERT INTO landlords (landlord_id, display_name, owner_key, created_at, updated_at) "
        "VALUES (?, ?, ?, 'now', 'now')",
        [(1, "Willow Lane Apartments Inc", "willow-lane-apartments-inc"),
         (2, "Kruthaups Holding Ltd", "kruthaups-holding-ltd"),
         (3, "Solo Rentals Ltd", "solo-rentals-ltd")],
    )
    conn.executemany(
        "INSERT INTO buildings (addr_key, address, lat, lon, local_area, units, landlord_id, "
        "created_at, updated_at) VALUES (?, ?, 49.28, -123.1, 'Mount Pleasant', 20, ?, 'now', 'now')",
        [("522 e 8th ave", "522 e 8th ave", 1),
         ("525 w 14th ave", "525 w 14th ave", 2),
         ("1 solo st", "1 solo st", 3),
         ("2 solo st", "2 solo st", 3),
         ("3 nobody st", "3 nobody st", None)],
    )
    conn.executemany(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, order_created_date, "
        "data_fetch_status, ingested_at) VALUES (?, ?, '2026-05-28 16:10:39.862', 'SUCCESS', 'now')",
        [("008-173-613", "ST. GEORGE ESTATES LTD."),
         ("007-265-280", "GLR PROPERTIES LTD."),
         ("007-265-281", "GLR PROPERTIES LTD.")],
    )
    conn.execute(
        "INSERT INTO raw_buildings (address, bsns_year, ingested_at) "
        "VALUES ('522 e 8th ave', 2026, 'now')"
    )
    conn.execute(
        "INSERT INTO overlay_housing (addr_key, address, housing_name, local_area, lat, lon, "
        "is_coop, is_sro, ingested_at) VALUES ('999 nowhere rd', '999 nowhere rd', 'Elm Co-op', "
        "'Mount Pleasant', 49.3, -123.15, 1, 0, 'now')"
    )
    for a, b in (("GLR PROPERTIES LTD.", "RENER, GEORGE"), ("ST. GEORGE ESTATES LTD.", "RENER, GEORGE")):
        record_claim(conn, a, b, "common_owner", "public_registry", confidence="confirmed")
    record_claim(conn, "GLR PROPERTIES LTD.", "ST. GEORGE ESTATES LTD.", "common_owner",
                 "tenant_report", confidence="confirmed", source_note=CANARY)
    conn.commit()
    pid_map = tmp_path / "pid_address_map.csv"
    pid_map.write_text(
        "pid,address_point_id,address,addr_key,local_area,lat_lon\n"
        '008173613,1,522 e 8th ave,522 e 8th ave,Mount Pleasant,"49.28,-123.1"\n'
        '007265280,2,525 w 14th ave,525 w 14th ave,Mount Pleasant,"49.28,-123.1"\n'
        '007265281,3,999 not rental st,999 not rental st,Mount Pleasant,"49.28,-123.1"\n',
        encoding="utf-8",
    )
    return str(pid_map)


def _export(tmp_path: Path, extra=None) -> Path:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    pid_map = _seed(conn, tmp_path)
    if extra:
        extra(conn)
    out = tmp_path / "out"
    export_artifacts(conn, out, pid_address_map_path=pid_map)
    return out


def _records(out: Path) -> dict:
    data = json.loads((out / "building_records.json").read_text())
    return {r["address"]: r for r in data["records"].values()}


def test_building_owner_is_its_registry_body_within_a_claims_network(tmp_path):
    rec = _records(_export(tmp_path))["522 e 8th ave"]
    assert (rec["owner_name"], rec["owner_key"], rec["owner_source"]) == (
        "ST. GEORGE ESTATES LTD.", "st-george-estates-ltd", "registry")
    assert rec["registered_owners"] == ["ST. GEORGE ESTATES LTD."]
    assert rec["registry_pids"] == ["008-173-613"]
    assert rec["registry_retrieved"] == "2026-05-28"
    assert rec["licence_holder"] == "Willow Lane Apartments Inc"
    assert (rec["network_key"], rec["network_name"], rec["network_source"], rec["network_name_source"]) == (
        "glr-properties-ltd", "GLR PROPERTIES LTD.", "claims", "default")
    assert rec["network_entities"] == ["GLR PROPERTIES LTD.", "RENER, GEORGE", "ST. GEORGE ESTATES LTD."]
    assert rec["network_buildings_on_map"] == 2
    assert rec["network_properties_on_title"] == 3
    assert rec["network_evidence"] == {"registry": 2, "vtu_research": 1}


def test_licence_only_buildings_fall_back_to_the_licence_holder(tmp_path):
    rec = _records(_export(tmp_path))["1 solo st"]
    assert (rec["owner_name"], rec["owner_key"], rec["owner_source"]) == (
        "Solo Rentals Ltd", "solo-rentals-ltd", "licence")
    assert rec["registered_owners"] == [] and rec["registry_pids"] == []
    assert rec["registry_retrieved"] is None
    assert (rec["network_key"], rec["network_name"], rec["network_source"]) == (
        "solo-rentals-ltd", "Solo Rentals Ltd", "licence")
    assert rec["network_buildings_on_map"] == 2
    assert rec["network_properties_on_title"] is None
    assert rec["network_entities"] is None and rec["network_evidence"] is None
    assert rec["network_name_source"] is None


def test_unknown_owners_carry_no_source_and_no_network_size(tmp_path):
    recs = _records(_export(tmp_path))
    for address in ("3 nobody st", "999 nowhere rd"):
        rec = recs[address]
        assert (rec["owner_name"], rec["owner_key"]) == ("(Unknown)", "unknown"), address
        assert rec["owner_source"] is None and rec["network_source"] is None, address
        assert rec["network_buildings_on_map"] is None, address


def test_network_label_claim_renames_the_network_but_not_its_key(tmp_path):
    def label(conn):
        record_claim(conn, "RENER, GEORGE", "GLR Properties / Rener family", NETWORK_LABEL,
                     "manual_research", confidence="confirmed")

    rec = _records(_export(tmp_path, label))["525 w 14th ave"]
    assert (rec["network_name"], rec["network_name_source"], rec["network_key"]) == (
        "GLR Properties / Rener family", "claim", "glr-properties-ltd")


def test_marker_metadata_carries_both_keys(tmp_path):
    markers = json.loads((_export(tmp_path) / "marker_metadata.json").read_text())["markers"]
    by_owner = {m["owner_key"]: m for m in markers}
    assert by_owner["st-george-estates-ltd"]["network_key"] == "glr-properties-ltd"


def test_filter_config_carries_the_licence_year(tmp_path):
    cfg = json.loads((_export(tmp_path) / "filter_config.json").read_text())
    assert cfg["licence_year"] == 2026


def test_claim_source_notes_never_reach_any_artifact(tmp_path):
    """Guard: passes before and after this change. Notes can identify tenants
    (CLAUDE.md §11), so no artifact may ever contain one."""
    out = _export(tmp_path)
    for path in out.iterdir():
        assert "CANARY-7f3a" not in path.read_text(encoding="utf-8"), path.name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_export_ownership.py -v`
Expected: every test except the canary guard fails with `KeyError` (`owner_name`, `network_key`, `licence_year`). The canary guard passes, which is expected, since it pins existing behaviour.

- [ ] **Step 3: Implement `reconstruct_points` ownership**

In `src/tc_core/export.py`, add these imports:

```python
from .metrics.registry_owners import build_registry_owners
from .normalize import sanitize_owner
```

In `reconstruct_points`, replace:

```python
    buildings = buildings.rename(
        columns={"building_id": "b_id", "display_name": "owner_group"}
    )
```

with:

```python
    buildings = buildings.rename(
        columns={"building_id": "b_id", "display_name": "licence_holder", "owner_key": "licence_key"}
    )
```

The two `fillna` lines above it (`"(Unknown)"` / `"unknown"`) stay unchanged. They run before the rename.

Replace the whole portfolio block, from the `# Claims-derived landlord portfolios` comment through `merged["owner_key"] = portfolio_key.fillna(merged["owner_key"])`, with:

```python
    # Two ownership layers (docs/superpowers/specs/2026-09-23-ownership-layers-design.md):
    # the building's own owner — its primary LOTR reporting body, else the
    # licence holder — and its network — the confirmed common_owner cluster
    # its PIDs reach, else the licence holder's group.
    registry = build_registry_owners(conn, pid_address_map_path) if pid_address_map_path else {}
    portfolios = (
        build_landlord_portfolios(conn, pid_address_map_path) if pid_address_map_path else {}
    )
    _assign_ownership(merged, registry, portfolios)
```

In the `merged = merged[[...]]` column list, replace `"owner_group",` / `"owner_key",` and `"portfolio_name", "portfolio_building_count",` / `"portfolio_entities",` so the list reads:

```python
    merged = merged[
        [
            "addr_key", "address", "lat", "lon", "units", "year_built", "n_issues", "issues_details",
            "member_count", "has_vtu_member", "member_share_building",
            "owner_name", "owner_key", "owner_source", "registered_owners", "registry_pids",
            "registry_retrieved", "licence_holder", "network_key", "network_name",
            "network_source", "network_name_source", "network_entities",
            "network_properties_on_title", "network_evidence",
            "member_count_all", "members_payload", "value_land",
            "value_bldg", "bldg_land_ratio", "local_area", "b_id", "block_id",
            "latest_membership_year", "source",
            *BUILDING_OVERLAY_COLUMNS,
        ]
    ]
```

After the `merged["housing_type"] = np.where(...)` statement, and before `return merged`, add:

```python
    on_map = merged.groupby("network_key")["b_id"].transform("count")
    merged["network_buildings_on_map"] = [
        None if key == "unknown" else int(count)
        for key, count in zip(merged["network_key"], on_map)
    ]
```

Add this helper directly after `reconstruct_points`:

```python
def _assign_ownership(df: pd.DataFrame, registry: dict, portfolios: dict) -> None:
    """Adds the owner_* and network_* columns in place (see the ownership-layers spec)."""
    reg = [registry.get(key) for key in df["addr_key"]]
    port = [portfolios.get(key) for key in df["addr_key"]]
    df["registered_owners"] = [r.owners if r else [] for r in reg]
    df["registry_pids"] = [r.pids if r else [] for r in reg]
    df["registry_retrieved"] = [r.retrieved if r else None for r in reg]
    df["owner_name"] = [r.owners[0] if r else lic for r, lic in zip(reg, df["licence_holder"])]
    df["owner_key"] = df["owner_name"].map(sanitize_owner)
    df["owner_source"] = [
        "registry" if r else ("licence" if key != "unknown" else None)
        for r, key in zip(reg, df["owner_key"])
    ]
    df["network_key"] = [p.portfolio_key if p else key for p, key in zip(port, df["licence_key"])]
    df["network_name"] = [p.portfolio_name if p else lic for p, lic in zip(port, df["licence_holder"])]
    df["network_source"] = [
        "claims" if p else ("licence" if key != "unknown" else None)
        for p, key in zip(port, df["network_key"])
    ]
    df["network_name_source"] = [p.name_source if p else None for p in port]
    df["network_entities"] = [list(p.entities) if p else None for p in port]
    df["network_properties_on_title"] = [len(p.addr_keys) if p else None for p in port]
    df["network_evidence"] = [dict(p.evidence) if p else None for p in port]
```

In `_append_overlay_housing`, replace:

```python
    overlay["owner_group"] = "(Unknown)"
    overlay["owner_key"] = "unknown"
```

with:

```python
    overlay["owner_name"] = "(Unknown)"
    overlay["owner_key"] = "unknown"
    overlay["licence_holder"] = "(Unknown)"
    overlay["network_key"] = "unknown"
    overlay["network_name"] = "(Unknown)"
    overlay["registered_owners"] = [[] for _ in range(len(overlay))]
    overlay["registry_pids"] = [[] for _ in range(len(overlay))]
```

- [ ] **Step 4: Implement markers, filter config and the public column list**

In `_marker_records`, after `"owner_key": r.get("owner_key"),` add:

```python
                "network_key": r.get("network_key"),
```

In `reconstruct_filter_config`, before `return cfg`, add:

```python
    cfg["licence_year"] = _licence_year(conn)
```

and add this helper above `reconstruct_filter_config`:

```python
def _licence_year(conn: sqlite3.Connection) -> int | None:
    """Business-licence data year of this build (raw_buildings.bsns_year)."""
    row = conn.execute("SELECT MAX(bsns_year) FROM raw_buildings").fetchone()
    return int(row[0]) if row and row[0] is not None else None
```

Replace the `BUILDING_RECORD_COLUMNS` comment and list with:

```python
# building_records.json's columns, in order. An explicit list, not "every
# column of points_df": the frontend's CSV export writes these verbatim, so
# lineage/ingest internals and — per the public/sensitive filter (spec
# §12) — VTU membership data must never reach it. Ownership is two layers:
# owner_* (the building's own owner) and network_* (its landlord network);
# claim provenance is public only as source-type counts, never notes.
BUILDING_RECORD_COLUMNS = [
    "b_id", "address", "local_area", "block_id", "units",
    "year_built", "owner_name", "owner_key", "owner_source",
    "registered_owners", "registry_pids", "registry_retrieved", "licence_holder",
    "network_key", "network_name", "network_source", "network_name_source",
    "network_entities", "network_buildings_on_map", "network_properties_on_title",
    "network_evidence",
    "value_land", "value_bldg", "bldg_land_ratio",
    "housing_type", "n_issues", "issues_details", "source",
    "lat", "lon",
    "in_chinatown", "in_village_plan",
    *BUILDING_OVERLAY_COLUMNS,
]
```

Update the module docstring's portfolio comment where it mentions `owner_group`, if any remains (`grep -n "owner_group\|portfolio_" src/tc_core/export.py` should return nothing afterwards).

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `uv run pytest tests/test_export_ownership.py -v`
Expected: 7 passed.

- [ ] **Step 6: Update the existing tests that read the old fields**

In `tests/test_export_source_discriminator.py`, replace `assert (overlay["owner_group"] == "(Unknown)").all()` with `assert (overlay["owner_name"] == "(Unknown)").all()`.

In `tests/test_export_artifacts.py`, replace `POPUP_FIELDS` with:

```python
POPUP_FIELDS = [
    "housing_name", "owner_name", "owner_source", "registered_owners", "registry_pids",
    "registry_retrieved", "licence_holder", "network_name", "network_source",
    "network_name_source", "network_entities", "network_buildings_on_map",
    "network_properties_on_title", "network_evidence",
    "coop_status", "coop_ownership_model", "coop_url",
    "sro_owner", "sro_operator", "sro_occupancy_status", "sro_registered_rooms",
]
```

Change that test's docstring to `"""Spec §7 plus the ownership-layers spec: the popup reads these fields."""`. In `test_building_records_columns_are_the_public_list`, add `"licence_key",` to the tuple of internal columns asserted absent.

- [ ] **Step 7: Regenerate the frontend fixtures**

Run: `uv run python scripts/make_frontend_fixtures.py`
Expected: `wrote …/frontend/fixtures`. `git diff --stat frontend/fixtures` shows `building_records.json`, `marker_metadata.json` and `filter_config.json` changed.

- [ ] **Step 8: Run both suites**

Run: `uv run pytest tests/ -q`
Expected: 106 passed.
Run: `cd frontend && npx vitest run`
Expected: 62 passed. The frontend tests build their own records and don't read the fixtures.

- [ ] **Step 9: Commit**

```bash
git add src/tc_core/export.py tests/test_export_ownership.py tests/test_export_artifacts.py tests/test_export_source_discriminator.py frontend/fixtures
git commit -m "Export owner and network as separate layers, with provenance fields"
```

---

### Task 6: Fixtures that exercise a claims network

**Files:**
- Modify: `scripts/make_frontend_fixtures.py`
- Modify: `tests/test_frontend_fixtures.py`
- Regenerate: `frontend/fixtures/*`

**Interfaces:**
- Consumes: the export contract (Task 5).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_frontend_fixtures.py`:

```python
def test_fixtures_exercise_registry_owners_and_a_claims_network():
    records = json.loads((FIXTURES / "building_records.json").read_text())["records"].values()
    assert any(r["owner_source"] == "registry" for r in records)
    assert any(r["network_source"] == "claims" for r in records)
    assert json.loads((FIXTURES / "filter_config.json").read_text())["licence_year"] == 2026
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_frontend_fixtures.py -v`
Expected: the new test fails with `assert False` on the first `any(...)`.

- [ ] **Step 3: Seed invented LOTR data in the generator**

In `scripts/make_frontend_fixtures.py`, add after `BUILDINGS`:

```python
# Invented registry filings: building 1's PID is reported by Example Holdings,
# building 2's by a nominee company; one invented person links both, so the
# fixtures carry a claims network and a registry owner that differs from the
# licence holder.
LOTR = [
    ("000-000-001", "EXAMPLE HOLDINGS LTD."),
    ("000-000-002", "INVENTED NOMINEE LTD."),
]
CLAIMS = [
    ("fixture-1", "EXAMPLE HOLDINGS LTD.", "INVENTED, PERSON"),
    ("fixture-2", "INVENTED NOMINEE LTD.", "INVENTED, PERSON"),
]
PID_ADDRESS_MAP = (
    "pid,address_point_id,address,addr_key,local_area,lat_lon\n"
    '000000001,1,100 Example St,100 example st,Northside,"49.281,-123.129"\n'
    '000000002,2,110 Example St,110 example st,Northside,"49.2812,-123.1288"\n'
)
```

At the end of `_seed`, before `conn.commit()`, add:

```python
    conn.executemany(
        "INSERT INTO raw_lotr_ownership (pid, reporting_body_name, order_created_date, "
        "data_fetch_status, ingested_at) VALUES (?, ?, '2026-01-01 00:00:00.000', 'SUCCESS', ?)",
        [(pid, name, TS) for pid, name in LOTR],
    )
    conn.executemany(
        "INSERT INTO ownership_claims (claim_key, entity_a, entity_b, relationship, source_type, "
        "confidence, status, created_at, updated_at) "
        "VALUES (?, ?, ?, 'common_owner', 'public_registry', 'confirmed', 'active', ?, ?)",
        [(key, a, b, TS, TS) for key, a, b in CLAIMS],
    )
    conn.execute(
        "INSERT INTO raw_buildings (address, bsns_year, ingested_at) VALUES ('100 example st', 2026, ?)",
        (TS,),
    )
```

In `build()`, inside the `with tempfile.TemporaryDirectory() as tmp:` block, add:

```python
        pid_map = Path(tmp) / "pid_address_map.csv"
        pid_map.write_text(PID_ADDRESS_MAP, encoding="utf-8")
```

and pass `pid_address_map_path=str(pid_map),` to `export_artifacts(...)`.

- [ ] **Step 4: Regenerate and verify**

Run: `uv run python scripts/make_frontend_fixtures.py && uv run pytest tests/test_frontend_fixtures.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 107 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/make_frontend_fixtures.py tests/test_frontend_fixtures.py frontend/fixtures
git commit -m "Seed fixtures with an invented registry owner and claims network"
```

---

### Task 7: Popup with owner, licence and network lines, and provenance

**Files:**
- Modify: `frontend/src/html.ts`, `frontend/src/html.test.ts`
- Modify: `frontend/src/popup.ts`, `frontend/src/popup.css`, `frontend/src/popup.test.ts`
- Modify: `frontend/src/types.ts`, `frontend/src/bootstrap.ts`

**Interfaces:**
- Consumes: the Task 5 record fields and `filter_config.licence_year`.
- Produces:
  - `html.sameName(a: string, b: string): boolean`
  - `popup.renderPopup(r: BuildingRecord, ctx?: PopupContext)`, where `PopupContext = { licenceYear?: number | null }`
  - exported `registryProvenance(pids: string[], retrieved: string)`, `licenceProvenance(year)` and `networkProvenance(r)`

- [ ] **Step 1: Write the failing tests**

In `frontend/src/html.test.ts`, add `sameName` to the import from `'./html'` and append:

```ts
describe('sameName', () => {
  it('ignores case, spacing and punctuation', () => {
    expect(sameName('GLR PROPERTIES LTD.', 'Glr Properties Ltd')).toBe(true);
    expect(sameName('GLR PROPERTIES LTD.', 'GLR Holdings Ltd')).toBe(false);
  });
});
```

Replace `frontend/src/popup.test.ts` with:

```ts
import { describe, expect, it } from 'vitest';
import {
  formatCurrencyCompact,
  licenceProvenance,
  networkProvenance,
  registryProvenance,
  renderPopup,
  safeUrl,
} from './popup';
import type { BuildingRecord } from './types';

const building: BuildingRecord = {
  b_id: 1, address: '522 E 8th Ave', housing_name: null,
  owner_name: 'ST. GEORGE ESTATES LTD.', owner_key: 'st-george-estates-ltd', owner_source: 'registry',
  registered_owners: ['ST. GEORGE ESTATES LTD.'], registry_pids: ['008-173-613'],
  registry_retrieved: '2026-05-28', licence_holder: 'Willow Lane Apartments Inc',
  network_key: 'glr-properties-ltd', network_name: 'GLR PROPERTIES LTD.', network_source: 'claims',
  network_name_source: 'default', network_entities: ['a', 'b', 'c', 'd', 'e', 'f'],
  network_buildings_on_map: 19, network_properties_on_title: 23,
  network_evidence: { registry: 36, vtu_research: 2 },
  units: 87.0, year_built: 1974.0, local_area: 'Mount Pleasant', value_land: 20100000, value_bldg: 950000,
  is_coop: false, is_sro: false,
};

describe('renderPopup', () => {
  it('leads with the ownership story', () => {
    const html = renderPopup(building);
    expect(html.indexOf('ST. GEORGE ESTATES LTD.')).toBeLessThan(html.indexOf('87 units'));
    expect(html).toContain('Licensed as Willow Lane Apartments Inc');
    expect(html).toContain('Part of the <strong>GLR PROPERTIES LTD.</strong> network');
    expect(html).toContain('19 buildings on map · 23 properties on title · 6 linked entities');
    expect(html).toContain('87 units · built 1974');
    expect(html).toContain('Assessed $20.1M land · $950K building');
  });

  it('carries no membership data (editorial choice, spec §7)', () => {
    // "VTU research" provenance is about ownership claims, not membership.
    expect(renderPopup(building)).not.toMatch(/member/i);
  });

  it('shows co-op and SRO sections only when they apply', () => {
    expect(renderPopup(building)).not.toMatch(/Co-op|SRO/);
    const html = renderPopup({
      ...building, is_coop: true, coop_status: 'Active', coop_ownership_model: 'Leasehold',
      coop_url: 'https://example.org/c', is_sro: true, sro_owner: 'X Ltd', sro_operator: 'Y Soc',
      sro_occupancy_status: 'Open', sro_registered_rooms: '42',
    });
    expect(html).toContain('Co-op · Active (Leasehold)');
    expect(html).toContain('<a href="https://example.org/c" target="_blank" rel="noopener">more info</a>');
    expect(html).toContain('SRO/SRA · Owner X Ltd · Operator Y Soc · Open · 42 rooms');
  });

  it('omits missing facts rather than printing blanks', () => {
    const html = renderPopup({ b_id: 9, address: '300 Invented Rd', owner_name: '(Unknown)', units: null, year_built: null });
    expect(html).not.toMatch(/units|built|Assessed|network|null|undefined/);
  });

  it('shows the outstanding-issues count only when there is one', () => {
    expect(renderPopup(building)).not.toMatch(/issue/i);
    expect(renderPopup({ ...building, n_issues: 0 })).not.toMatch(/issue/i);
    expect(renderPopup({ ...building, n_issues: 1 })).toContain('1 outstanding issue<');
    expect(renderPopup({ ...building, n_issues: 3 })).toContain('3 outstanding issues');
  });

  it('links to the City details page for an issue, only when a safe URL is present', () => {
    const withUrl = renderPopup({
      ...building, n_issues: 2,
      issues_details: 'http://app.vancouver.ca/RPS_Net/Default.aspx?num=1234&street=DAVIE%20ST',
    });
    expect(withUrl).toContain(
      '<a href="http://app.vancouver.ca/RPS_Net/Default.aspx?num=1234&amp;street=DAVIE%20ST" target="_blank" rel="noopener">City details</a>',
    );
    expect(renderPopup({ ...building, n_issues: 2 })).not.toContain('<a');
    expect(renderPopup({ ...building, n_issues: 2, issues_details: 'javascript:alert(1)' })).not.toContain('<a');
  });

  it('escapes every value', () => {
    const html = renderPopup({ ...building, address: '<img src=x onerror=alert(1)>', owner_name: 'A & B' });
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
    expect(html).toContain('A &amp; B');
    expect(html).not.toContain('<img');
  });
});

describe('ownership lines', () => {
  it('tags the registry owner with its PID and retrieval date', () => {
    expect(renderPopup(building)).toContain(
      'data-tip="BC Land Owner Transparency Registry: PID 008-173-613, record retrieved 2026-05-28"',
    );
  });

  it('skips the licence line when it only differs in case or punctuation', () => {
    expect(renderPopup({ ...building, licence_holder: 'St. George Estates Ltd' })).not.toContain('Licensed as');
  });

  it('tags a licence-sourced owner with the licence year and shows no licence line', () => {
    const html = renderPopup(
      { ...building, owner_source: 'licence', owner_name: 'Solo Rentals Ltd', licence_holder: 'Solo Rentals Ltd' },
      { licenceYear: 2026 },
    );
    expect(html).toContain('data-tip="City of Vancouver business licence, 2026"');
    expect(html).not.toContain('Licensed as');
  });

  it('counts co-owners', () => {
    expect(renderPopup({ ...building, registered_owners: ['ST. GEORGE ESTATES LTD.', 'OTHER LTD.'] }))
      .toContain('+1 co-owner<');
  });

  it('shows a licence network only when it spans more than one building', () => {
    const lic = {
      ...building, network_source: 'licence', network_name: 'Solo Rentals Ltd',
      network_entities: null, network_properties_on_title: null, network_evidence: null,
    };
    expect(renderPopup({ ...lic, network_buildings_on_map: 1 })).not.toContain('network');
    const html = renderPopup({ ...lic, network_buildings_on_map: 3 });
    expect(html).toContain('Part of the <strong>Solo Rentals Ltd</strong> network');
    expect(html).toContain('>3 buildings on map<');
    expect(html).toContain('data-tip="Grouped by business licence name"');
  });

  it('shows no provenance for an unknown owner', () => {
    const html = renderPopup({ b_id: 9, address: '999 Nowhere Rd', owner_name: '(Unknown)', owner_source: null, network_source: null });
    expect(html).toContain('(Unknown)');
    expect(html).not.toContain('class="prov"');
    expect(html).not.toContain('network');
  });

  it('escapes provenance text', () => {
    const html = renderPopup({ ...building, registry_pids: ['"><img src=x>'] });
    expect(html).not.toContain('<img');
    expect(html).toContain('&quot;&gt;&lt;img src=x&gt;');
  });
});

describe('provenance text', () => {
  it('lists up to three PIDs', () => {
    expect(registryProvenance(['1', '2', '3', '4', '5'], '')).toBe(
      'BC Land Owner Transparency Registry: PIDs 1, 2, 3 (+2 more)',
    );
  });

  it('omits the licence year when unknown', () => {
    expect(licenceProvenance(null)).toBe('City of Vancouver business licence');
  });

  it('summarizes network evidence and the naming rule', () => {
    expect(networkProvenance(building)).toBe(
      'Grouped from 36 provincial registry filings and 2 VTU research claims. Name: default (entity with the most properties).',
    );
    expect(networkProvenance({ ...building, network_evidence: { registry: 1, vtu_research: 0 }, network_name_source: 'claim' }))
      .toBe('Grouped from 1 provincial registry filing. Name: set by claim.');
  });
});

describe('helpers', () => {
  it('formats assessed values compactly', () => {
    expect(formatCurrencyCompact(20186619)).toBe('$20.2M');
    expect(formatCurrencyCompact(950000)).toBe('$950K');
    expect(formatCurrencyCompact(640)).toBe('$640');
  });

  it('only links http(s) URLs', () => {
    expect(safeUrl('https://example.org/x')).toBe('https://example.org/x');
    expect(safeUrl('javascript:alert(1)')).toBeNull();
    expect(safeUrl('not a url')).toBeNull();
    expect(safeUrl(null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/popup.test.ts src/html.test.ts`
Expected: FAIL. `sameName`, `licenceProvenance`, `networkProvenance` and `registryProvenance` are not exported, and the ownership assertions fail.

- [ ] **Step 3: Implement**

Append to `frontend/src/html.ts`:

```ts
/** Same name once case, spacing and punctuation are ignored ("GLR PROPERTIES LTD." ~ "Glr Properties Ltd"). */
export function sameName(a: string, b: string): boolean {
  const key = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
  return key(a) === key(b);
}
```

In `frontend/src/popup.ts`:
- Change the import to `import { escapeHtml, isMissing, sameName } from './html';`.
- Below `const div = …`, add:

```ts
const strList = (v: unknown): string[] => (Array.isArray(v) ? v.map(str).filter(Boolean) : []);

export interface PopupContext {
  /** Business-licence data year (filter_config.licence_year). */
  licenceYear?: number | null;
}

export function registryProvenance(pids: string[], retrieved: string): string {
  const shown = pids.slice(0, 3).join(', ');
  const more = pids.length > 3 ? ` (+${pids.length - 3} more)` : '';
  const pidText = pids.length ? `: ${pids.length === 1 ? 'PID' : 'PIDs'} ${shown}${more}` : '';
  const when = retrieved ? `, record retrieved ${retrieved}` : '';
  return `BC Land Owner Transparency Registry${pidText}${when}`;
}

export function licenceProvenance(year: number | null | undefined): string {
  return year ? `City of Vancouver business licence, ${year}` : 'City of Vancouver business licence';
}

export function networkProvenance(r: BuildingRecord): string {
  if (str(r.network_source) !== 'claims') return 'Grouped by business licence name';
  const ev = (r.network_evidence ?? {}) as Record<string, unknown>;
  const registry = num(ev.registry) ?? 0;
  const research = num(ev.vtu_research) ?? 0;
  const parts = [
    registry ? plural(registry, 'provincial registry filing', 'provincial registry filings') : '',
    research ? plural(research, 'VTU research claim', 'VTU research claims') : '',
  ].filter(Boolean);
  const grouped = parts.length ? `Grouped from ${parts.join(' and ')}.` : 'Grouped from ownership claims.';
  const name = str(r.network_name_source) === 'claim'
    ? 'Name: set by claim.'
    : 'Name: default (entity with the most properties).';
  return `${grouped} ${name}`;
}

/** Small "i" marker; its source text shows on hover or on focus (a tap on touch screens). */
function provenance(text: string): string {
  const t = escapeHtml(text);
  return `<span class="prov" tabindex="0" role="note" aria-label="Source: ${t}" data-tip="${t}">i</span>`;
}

function ownershipLines(r: BuildingRecord, ctx: PopupContext): string[] {
  const lines: string[] = [];
  const owner = str(r.owner_name);
  const ownerSource = str(r.owner_source);
  if (owner) {
    let html = escapeHtml(owner);
    if (ownerSource === 'registry') html += provenance(registryProvenance(strList(r.registry_pids), str(r.registry_retrieved)));
    else if (ownerSource === 'licence') html += provenance(licenceProvenance(ctx.licenceYear));
    const coOwners = strList(r.registered_owners).length - 1;
    if (coOwners > 0) html += ` <span class="popup-muted">${escapeHtml(`+${plural(coOwners, 'co-owner', 'co-owners')}`)}</span>`;
    lines.push(div('popup-owner', html));
  }
  const licence = str(r.licence_holder);
  if (ownerSource === 'registry' && licence && licence !== '(Unknown)' && !sameName(licence, owner)) {
    lines.push(div('', escapeHtml(`Licensed as ${licence}`) + provenance(licenceProvenance(ctx.licenceYear))));
  }
  const netSource = str(r.network_source);
  const onMap = num(r.network_buildings_on_map);
  if (netSource === 'claims' || (netSource === 'licence' && onMap !== null && onMap > 1)) {
    lines.push(div('', `Part of the <strong>${escapeHtml(str(r.network_name))}</strong> network${provenance(networkProvenance(r))}`));
    const onTitle = num(r.network_properties_on_title);
    const entities = strList(r.network_entities).length;
    const counts = [
      onMap === null ? '' : `${plural(Math.trunc(onMap), 'building', 'buildings')} on map`,
      onTitle === null ? '' : `${plural(Math.trunc(onTitle), 'property', 'properties')} on title`,
      entities ? plural(entities, 'linked entity', 'linked entities') : '',
    ].filter(Boolean).join(' · ');
    if (counts) lines.push(div('popup-muted', escapeHtml(counts)));
  }
  return lines;
}
```

- In `renderPopup`, change the signature to `export function renderPopup(r: BuildingRecord, ctx: PopupContext = {}): string {`. Replace the `const ownership: string[] = [];` block, through the closing `}` of the `if (str(r.portfolio_name)) { … }` block, with `const ownership = ownershipLines(r, ctx);`.

Append to `frontend/src/popup.css`:

```css
.tc-popup .popup-muted { color: #666; font-weight: 400; }
.tc-popup .prov {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  margin-left: 4px;
  border: 1px solid #8a8f9c;
  border-radius: 50%;
  font: italic 700 9px/1 Georgia, serif;
  color: #5b6070;
  vertical-align: 1px;
  cursor: help;
}
.tc-popup .prov:focus { outline: 2px solid #6b8fd6; outline-offset: 1px; }
.tc-popup .prov::after {
  content: attr(data-tip);
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  width: max-content;
  max-width: 220px;
  padding: 5px 7px;
  border-radius: 4px;
  background: #1f2330;
  color: #fff;
  font: 400 11px/1.35 system-ui, sans-serif;
  white-space: normal;
  text-align: left;
  z-index: 10;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.1s;
}
.tc-popup .prov:hover::after,
.tc-popup .prov:focus::after { opacity: 1; }
```

In `frontend/src/types.ts`:
- Add `network_key: string | null;` to `MarkerRecord` after `owner_key`. `tsconfig` type-checks `src/`, so also update the `base` literal in `frontend/src/markers.test.ts`: replace `owner_key: 'x',` with `owner_key: 'x', network_key: 'x',`.
- Add `licence_year?: number | null;` to `FilterConfig`.
- Change the `BuildingRecord` doc comment from "the 41 columns" to "the columns".

In `frontend/src/bootstrap.ts`, replace the `bindPopup` line with:

```ts
    marker.bindPopup(
      () => renderPopup(records[String(m.b_id)] ?? { b_id: m.b_id }, { licenceYear: artifacts.filterConfig.licence_year ?? null }),
      { maxWidth: 320 },
    );
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/popup.test.ts src/html.test.ts`
Expected: all pass.

- [ ] **Step 5: Full frontend checks**

Run: `cd frontend && npx vitest run && npx tsc --noEmit -p . && npx vite build --logLevel error`
Expected: every test passes, and typecheck and build are clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/html.ts frontend/src/html.test.ts frontend/src/popup.ts frontend/src/popup.css frontend/src/popup.test.ts frontend/src/types.ts frontend/src/bootstrap.ts frontend/src/markers.test.ts
git commit -m "Popup: separate owner, licence and network lines with provenance tooltips"
```

---

### Task 8: Buildings tab shows Owner and Network

**Files:**
- Modify: `frontend/src/tables.ts`, `frontend/src/tables.test.ts`, `frontend/index.html`

**Interfaces:**
- Consumes: `html.sameName` (Task 7).
- Produces: building rows with `data-network="<network_key>"` right after `data-owner`, and Owner and Network cells.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/tables.test.ts`, change the `rec` defaults from `owner_group: 'O', owner_key: 'o',` to:

```ts
  year_built: 1970, owner_name: 'O', owner_key: 'o', network_name: 'O', network_key: 'o',
```

(Keep the rest of that line.) Replace the first `buildingRow` test body with:

```ts
    const row = buildingRow(rec({
      b_id: 7, address: '12 Oak & Elm St', block_id: 3.0, units: 40.0,
      year_built: 1965.0, owner_name: 'Example "Holdings"', owner_key: 'example-holdings',
      network_name: 'Example Group', network_key: 'example-group',
      value_land: 5000000.4, value_bldg: 800000.0, bldg_land_ratio: 0.16, housing_type: 'sro',
    }));
    expect(row).toBe(
      '<tr data-bid="7" data-owner="example-holdings" data-network="example-group" data-block="3" data-area="West End" ' +
        'data-chinatown="" data-village="" ' +
        'data-value-land="5000000" data-value-bldg="800000" data-value-ratio="0.16" data-units="40" ' +
        'data-year-built="1965" data-search="12 oak &amp; elm st west end 40 example &quot;holdings&quot; example group sro" ' +
        'data-housing-type="sro" data-n-issues="">' +
        '<td class="select-cell"><input type="checkbox" class="row-select" data-type="building" data-target="7"></td>' +
        '<td>12 Oak &amp; Elm St</td><td data-sort-value="West End">West End</td>' +
        '<td data-sort-value="40">40</td>' +
        '<td>Example &quot;Holdings&quot;</td><td>Example Group</td>' +
        '<td data-sort-value="1965">1965</td><td data-sort-value="sro">sro</td></tr>',
    );
```

and add to the `buildingRow` describe block:

```ts
  it('leaves the network cell blank when it names the owner again', () => {
    const row = buildingRow(rec({ owner_name: 'GLR PROPERTIES LTD.', network_name: 'Glr Properties Ltd' }));
    expect(row).toContain('<td>GLR PROPERTIES LTD.</td><td></td>');
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/tables.test.ts`
Expected: FAIL. The first `buildingRow` test and the new blank-cell test fail.

- [ ] **Step 3: Implement**

In `frontend/src/tables.ts`:
- Change the import to `import { escapeHtml, isMissing, roundHalfEven, sameName } from './html';`.
- In `buildingRow`, replace `const owner = text(r.owner_group);` and the `search` construction with:

```ts
  const owner = text(r.owner_name);
  const networkName = text(r.network_name);
  const network = sameName(networkName, owner) ? '' : networkName;
  const search = [text(r.address), area, units, owner, network, housing]
```

(Keep the `.filter(...).map(...).join(' ')` chain that follows.)
- Replace the row's first template line with:

```ts
    `<tr data-bid="${bid}" data-owner="${escapeHtml(text(r.owner_key))}" ` +
    `data-network="${escapeHtml(text(r.network_key))}" data-block="${block}" ` +
```

- Replace `` `<td>${escapeHtml(owner)}</td>` + `` with:

```ts
    `<td>${escapeHtml(owner)}</td>` +
    `<td>${escapeHtml(network)}</td>` +
```

In `frontend/index.html`, in the buildings table header, replace `<th data-sort="text">Landlord</th>` with:

```html
              <th data-sort="text">Owner</th>
              <th data-sort="text">Network</th>
```

and in its `tfoot` replace `<td colspan="3" id="summary-buildings-rows">0 rows</td>` with `<td colspan="4" id="summary-buildings-rows">0 rows</td>`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/tables.test.ts`
Expected: all pass. The `group tables` landlord test still passes because its records set `owner_group` explicitly. Task 9 replaces it.

- [ ] **Step 5: Full frontend checks**

Run: `cd frontend && npx vitest run && npx tsc --noEmit -p . && npx vite build --logLevel error`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/tables.ts frontend/src/tables.test.ts frontend/index.html
git commit -m "Buildings tab: show Owner and Network columns"
```

---

### Task 9: Landlords tab Owners | Networks toggle

**Files:**
- Create: `frontend/src/view-toggle.ts`, `frontend/src/view-toggle.test.ts`
- Modify: `frontend/src/tables.ts`, `frontend/src/tables.test.ts`, `frontend/src/page-layout.test.ts`, `frontend/index.html`, `frontend/src/wiring.js`, `frontend/src/bootstrap.ts`

**Interfaces:**
- Consumes: Task 5 fields, the `data-network` building rows (Task 8), and `network_key` on markers.
- Produces:
  - `tables.ownerRowsHtml(records)` (rows `data-owner`, `data-type="owner"`)
  - `tables.networkRowsHtml(records)` (rows `data-network`, `data-type="network"`); `landlordRowsHtml` is removed
  - `view-toggle.initViewToggle(options: { button: HTMLElement; panel: HTMLElement }[])`
  - DOM ids `owners-table`, `networks-table`, `owners-panel`, `networks-panel`, `landlord-view-owners`, `landlord-view-networks`, and `summary-{owners,networks}-{label,bldgs,units,avg}`

- [ ] **Step 1: Write the failing tests**

In `frontend/src/tables.test.ts`, replace `landlordRowsHtml` in the import with `networkRowsHtml, ownerRowsHtml`, and replace the `group tables` describe block's `records` and landlord test with:

```ts
  const records = [
    rec({ b_id: 1, owner_name: 'B Co', owner_key: 'b', network_name: 'Net', network_key: 'net', units: 10, local_area: 'West End' }),
    rec({ b_id: 2, owner_name: 'A Co', owner_key: 'a', network_name: 'Net', network_key: 'net', units: 30, local_area: null }),
    rec({ b_id: 3, owner_name: 'B Co', owner_key: 'b', network_name: 'Other', network_key: 'other', units: 5, local_area: 'West End' }),
  ];

  it('groups owners, sorted by total units', () => {
    const html = ownerRowsHtml(records);
    expect([...html.matchAll(/data-owner="([^"]+)"/g)].map((m) => m[1])).toEqual(['a', 'b']);
    expect(html).toContain('data-owner="b" data-bldgs="2" data-units="15"');
    expect(html).toContain('data-type="owner" data-target="b"');
  });

  it('groups networks, sorted by total units', () => {
    const html = networkRowsHtml(records);
    expect([...html.matchAll(/data-network="([^"]+)"/g)].map((m) => m[1])).toEqual(['net', 'other']);
    expect(html).toContain('data-network="net" data-bldgs="2" data-units="40"');
    expect(html).toContain('data-type="network" data-target="net"');
  });
```

(Keep the neighbourhoods test.)

Create `frontend/src/view-toggle.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { initViewToggle } from './view-toggle';

class FakeClassList {
  private names = new Set<string>();
  add(name: string) { this.names.add(name); }
  contains(name: string) { return this.names.has(name); }
  toggle(name: string, on: boolean) {
    if (on) this.names.add(name);
    else this.names.delete(name);
    return on;
  }
}

class FakeButton extends EventTarget {
  classList = new FakeClassList();
  attrs: Record<string, string> = {};
  setAttribute(name: string, value: string) { this.attrs[name] = value; }
}

function setup() {
  const networks = { button: new FakeButton(), panel: { hidden: false } };
  const owners = { button: new FakeButton(), panel: { hidden: false } };
  networks.button.classList.add('active');
  initViewToggle([networks, owners] as unknown as Parameters<typeof initViewToggle>[0]);
  return { networks, owners };
}

describe('initViewToggle', () => {
  it('shows the initially active view and hides the others', () => {
    const { networks, owners } = setup();
    expect(networks.panel.hidden).toBe(false);
    expect(owners.panel.hidden).toBe(true);
    expect(networks.button.attrs['aria-pressed']).toBe('true');
    expect(owners.button.attrs['aria-pressed']).toBe('false');
  });

  it('switches views on click', () => {
    const { networks, owners } = setup();
    owners.button.dispatchEvent(new Event('click'));
    expect(owners.panel.hidden).toBe(false);
    expect(networks.panel.hidden).toBe(true);
    expect(owners.button.classList.contains('active')).toBe(true);
    expect(networks.button.classList.contains('active')).toBe(false);
  });
});
```

Append to `frontend/src/page-layout.test.ts`:

```ts
const wiring = readFileSync(new URL('./wiring.js', import.meta.url), 'utf8');

describe('Landlords tab', () => {
  it('has an Owners and a Networks table with the totals cells wiring.js fills', () => {
    const ids = [
      'owners-table', 'networks-table', 'owners-panel', 'networks-panel',
      'landlord-view-owners', 'landlord-view-networks',
      ...['owners', 'networks'].flatMap((t) => ['label', 'bldgs', 'units', 'avg'].map((c) => `summary-${t}-${c}`)),
    ];
    for (const id of ids) expect(page).toContain(`id="${id}"`);
    expect(page).not.toContain('id="landlords-table"');
  });

  it('is wired for both views', () => {
    expect(wiring).toContain("'#owners-table tbody tr'");
    expect(wiring).toContain("'#networks-table tbody tr'");
    expect(wiring).toContain("typ === 'network'");
    expect(wiring).not.toMatch(/landlords-table|summary-landlords/);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/tables.test.ts src/view-toggle.test.ts src/page-layout.test.ts`
Expected: FAIL. `ownerRowsHtml`/`networkRowsHtml` and `./view-toggle` are missing, and the markup and wiring assertions fail.

- [ ] **Step 3: Implement the table rows and the toggle module**

In `frontend/src/tables.ts`:
- Change `groupRow`'s `type` parameter to `'owner' | 'network' | 'neighbourhood'`.
- Replace `landlordRowsHtml` with:

```ts
export function ownerRowsHtml(records: BuildingRecord[]): string {
  return aggregate(
    records,
    (r) => (isMissing(r.owner_name) ? '(Unknown)' : String(r.owner_name)),
    (r) => (isMissing(r.owner_key) ? 'unknown' : String(r.owner_key)),
  )
    .map((g) => groupRow(g, 'owner', escapeHtml(g.key), escapeHtml(g.label), 'data-owner'))
    .join('\n');
}

export function networkRowsHtml(records: BuildingRecord[]): string {
  return aggregate(
    records,
    (r) => (isMissing(r.network_name) ? '(Unknown)' : String(r.network_name)),
    (r) => (isMissing(r.network_key) ? 'unknown' : String(r.network_key)),
  )
    .map((g) => groupRow(g, 'network', escapeHtml(g.key), escapeHtml(g.label), 'data-network'))
    .join('\n');
}
```

- In `renderTables`, replace `fill('landlords-table', landlordRowsHtml(records));` with:

```ts
  fill('owners-table', ownerRowsHtml(records));
  fill('networks-table', networkRowsHtml(records));
```

Create `frontend/src/view-toggle.ts`:

```ts
/** Segmented control: shows the panel of the pressed button and hides the others. */
export interface ToggleOption {
  button: HTMLElement;
  panel: HTMLElement;
}

export function initViewToggle(options: ToggleOption[]): void {
  const show = (active: ToggleOption) => {
    for (const o of options) {
      const on = o === active;
      o.panel.hidden = !on;
      o.button.classList.toggle('active', on);
      o.button.setAttribute('aria-pressed', String(on));
    }
  };
  for (const o of options) o.button.addEventListener('click', () => show(o));
  const initial = options.find((o) => o.button.classList.contains('active')) ?? options[0];
  if (initial) show(initial);
}
```

- [ ] **Step 4: Implement the markup**

In `frontend/index.html`, replace the whole `<div id="pane-landlords" class="pane"> … </div>` block (its `table-wrap`, `#landlords-table` and `tfoot`) with:

```html
    <div id="pane-landlords" class="pane">
      <div class="view-toggle" role="group" aria-label="Group landlords by">
        <button type="button" id="landlord-view-networks" class="active" aria-pressed="true">Networks</button>
        <button type="button" id="landlord-view-owners" aria-pressed="false">Owners</button>
      </div>
      <div class="table-wrap" id="networks-panel">
        <table class="data" id="networks-table">
          <thead>
            <tr>
              <th class="select-head" data-sort="none">Select</th>
              <th data-sort="text">Network</th>
              <th data-sort="number">Bldgs</th>
              <th data-sort="number">Units</th>
              <th data-sort="number">Avg Units/Bldg</th>
            </tr>
          </thead>
          <tbody></tbody>
          <tfoot>
            <tr class="summary-row">
              <td></td>
              <td id="summary-networks-label">Totals (visible)</td>
              <td id="summary-networks-bldgs">0</td>
              <td id="summary-networks-units">0</td>
              <td id="summary-networks-avg">0.0</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div class="table-wrap" id="owners-panel" hidden>
        <table class="data" id="owners-table">
          <thead>
            <tr>
              <th class="select-head" data-sort="none">Select</th>
              <th data-sort="text">Owner</th>
              <th data-sort="number">Bldgs</th>
              <th data-sort="number">Units</th>
              <th data-sort="number">Avg Units/Bldg</th>
            </tr>
          </thead>
          <tbody></tbody>
          <tfoot>
            <tr class="summary-row">
              <td></td>
              <td id="summary-owners-label">Totals (visible)</td>
              <td id="summary-owners-bldgs">0</td>
              <td id="summary-owners-units">0</td>
              <td id="summary-owners-avg">0.0</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
```

In the `<style>` block, after the `.table-wrap { … }` rule, add:

```css
  .table-wrap[hidden] {
    display: none;
  }

  .view-toggle {
    display: flex;
    padding: 10px 12px 0;
  }

  .view-toggle button {
    flex: 1;
    padding: 5px 10px;
    border: 1px solid #cdd1dd;
    background: #fff;
    font-size: 12px;
    font-weight: 600;
    color: #27354a;
    cursor: pointer;
  }

  .view-toggle button + button {
    border-left: none;
  }

  .view-toggle button:first-child {
    border-radius: 4px 0 0 4px;
  }

  .view-toggle button:last-child {
    border-radius: 0 4px 4px 0;
  }

  .view-toggle button.active {
    background: #e6ecf7;
  }
```

- [ ] **Step 5: Wire the network index in `frontend/src/wiring.js`**

Make these nine edits.

1. Replace `      window.ownerIndex = {};` with:

```js
      window.ownerIndex = {};
      window.networkIndex = {};
```

2. After the `ownerKey` block in the marker-metadata loop (the one ending `window.ownerIndex[ownerKey].push(marker);` plus its two closing braces), add:

```js

          var networkKey = meta.network_key;
          if (networkKey) {
            if (!window.networkIndex[networkKey]) window.networkIndex[networkKey] = [];
            if (window.networkIndex[networkKey].indexOf(marker) === -1) {
              window.networkIndex[networkKey].push(marker);
            }
          }
```

3. After `function setOwnerSelection(…) { … }`, add:

```js

      function setNetworkSelection(networkKey, selected) {
        var arr = window.networkIndex[networkKey] || [];
        arr.forEach(function(marker) {
          adjustMarkerSelection(marker, selected ? +1 : -1);
        });
      }
```

4. After `function ownerHover(…) { … }`, add:

```js

      function networkHover(networkKey, on) {
        var arr = window.networkIndex[networkKey] || [];
        arr.forEach(function(marker) {
          if (!marker || marker._isFiltered) return;
          if (on) {
            highlightMarker(marker, true);
          } else if ((marker._selectionRefs || 0) === 0) {
            highlightMarker(marker, false);
          }
        });
      }
```

5. In `handleSelectionChange`, replace:

```js
        } else if (typ === 'owner') {
          setOwnerSelection(key, cb.checked);
```

with:

```js
        } else if (typ === 'owner') {
          setOwnerSelection(key, cb.checked);
        } else if (typ === 'network') {
          setNetworkSelection(key, cb.checked);
```

6. Replace the hover-listener block:

```js
      document.querySelectorAll('#landlords-table tbody tr').forEach(function(row) {
        var key = row.getAttribute('data-owner');
        row.addEventListener('mouseenter', function() { ownerHover(key, true); });
        row.addEventListener('mouseleave', function() { ownerHover(key, false); });
      });
```

with:

```js
      document.querySelectorAll('#owners-table tbody tr').forEach(function(row) {
        var key = row.getAttribute('data-owner');
        row.addEventListener('mouseenter', function() { ownerHover(key, true); });
        row.addEventListener('mouseleave', function() { ownerHover(key, false); });
      });

      document.querySelectorAll('#networks-table tbody tr').forEach(function(row) {
        var key = row.getAttribute('data-network');
        row.addEventListener('mouseenter', function() { networkHover(key, true); });
        row.addEventListener('mouseleave', function() { networkHover(key, false); });
      });
```

7. Replace:

```js
      const landlordRows = Array.from(document.querySelectorAll('#landlords-table tbody tr'));
      landlordRows.forEach(function(row) { row.__checkbox = row.querySelector('.row-select'); });
      cacheRowCells(landlordRows, { bldgs: 2, units: 3, avg: 4 });
```

with:

```js
      const ownerRows = Array.from(document.querySelectorAll('#owners-table tbody tr'));
      ownerRows.forEach(function(row) { row.__checkbox = row.querySelector('.row-select'); });
      cacheRowCells(ownerRows, { bldgs: 2, units: 3, avg: 4 });

      const networkRows = Array.from(document.querySelectorAll('#networks-table tbody tr'));
      networkRows.forEach(function(row) { row.__checkbox = row.querySelector('.row-select'); });
      cacheRowCells(networkRows, { bldgs: 2, units: 3, avg: 4 });
```

8. In `updateGroupTableSummaries`, replace the `landlordRows` call with:

```js
        updateGroupTableSummary(ownerRows, {
          label: 'summary-owners-label', bldgs: 'summary-owners-bldgs',
          units: 'summary-owners-units', avg: 'summary-owners-avg',
        });
        updateGroupTableSummary(networkRows, {
          label: 'summary-networks-label', bldgs: 'summary-networks-bldgs',
          units: 'summary-networks-units', avg: 'summary-networks-avg',
        });
```

9. In `applyFilters`, replace the `landlordRows.forEach(function(row) { … });` loop with:

```js
        ownerRows.forEach(function(row) {
          var owner = row.getAttribute('data-owner');
          var markers = window.ownerIndex[owner] || [];
          var hasVisible = markers.some(function(m) { return !m._isFiltered; });
          row.classList.toggle('hidden', !hasVisible);
          const checkbox = row.__checkbox;
          if (!hasVisible && checkbox && checkbox.checked) {
            checkbox.checked = false;
            setOwnerSelection(owner, false);
          }
          updateGroupRowValues(row, markers);
        });

        networkRows.forEach(function(row) {
          var network = row.getAttribute('data-network');
          var markers = window.networkIndex[network] || [];
          var hasVisible = markers.some(function(m) { return !m._isFiltered; });
          row.classList.toggle('hidden', !hasVisible);
          const checkbox = row.__checkbox;
          if (!hasVisible && checkbox && checkbox.checked) {
            checkbox.checked = false;
            setNetworkSelection(network, false);
          }
          updateGroupRowValues(row, markers);
        });
```

Then confirm that no reference is left over: `grep -n "landlordRows\|landlords-table\|summary-landlords" frontend/src/wiring.js` prints nothing.

- [ ] **Step 6: Hook the toggle up in `frontend/src/bootstrap.ts`**

Add `import { initViewToggle } from './view-toggle';` next to the other imports. At the end of `main()`, after the clear-button lines, add:

```ts
  const landlordViews = ['networks', 'owners'].map((v) => ({
    button: document.getElementById(`landlord-view-${v}`),
    panel: document.getElementById(`${v}-panel`),
  }));
  if (landlordViews.every((o) => o.button && o.panel)) {
    initViewToggle(landlordViews as { button: HTMLElement; panel: HTMLElement }[]);
  }
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd frontend && npx vitest run && npx tsc --noEmit -p . && npx vite build --logLevel error`
Expected: every test passes (62 + the Task 7, 8 and 9 additions), typecheck is clean, and the build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/tables.ts frontend/src/tables.test.ts frontend/src/view-toggle.ts frontend/src/view-toggle.test.ts frontend/src/page-layout.test.ts frontend/index.html frontend/src/wiring.js frontend/src/bootstrap.ts
git commit -m "Landlords tab: Owners | Networks toggle with separate selection and hover"
```

---

### Task 10: Docs, real rebuild, manual check

**Files:**
- Modify: `CLAUDE.md`, `docs/DATA_SOURCES.md`, `docs/superpowers/specs/2026-09-23-ownership-layers-design.md`

- [ ] **Step 1: Update CLAUDE.md**

- In "Claims ingestion & entity resolution", after the `resolve_entity_clusters()` bullet, add:

```markdown
- `network_label` claims name a landlord network: `entity_a` is any entity in a `common_owner` cluster, `entity_b` the display label — free text, stored verbatim, and excluded from `list_known_entities()`/`find_similar_entity()`. The most recently updated confirmed, active label on any entity in the cluster wins; without one the network is named after the entity holding the most PIDs. Relabelling never changes a network's key.
```

- In "Sensitivity model (Q11)", append the paragraph:

```markdown
**Public ownership data (2026-09-23).** LOTR reporting bodies and interest holders — including private individuals — are shown on the public map as the province publishes them; owners can seek removal through the registry's own channels. Claim provenance in public artifacts is limited to source *types* and counts: `public_registry` shows as "provincial registry", every other type collapses to "VTU research" so the map never signals that a tenant reported on a landlord, and `source_note` never leaves the database (a canary test in `tests/test_export_ownership.py` enforces this). Full provenance is for the internal app.
```

- Under Phase 1, **Public map**, add `- [x] Separate each building's owner (LOTR reporting body or licence holder) from its landlord network, with provenance indicators — see docs/superpowers/specs/2026-09-23-ownership-layers-design.md`.
- Set `Last updated:` to `2026-09-23`.

- [ ] **Step 2: Update DATA_SOURCES.md and the spec**

In `docs/DATA_SOURCES.md`, in the `buildings.csv` notes list (next to the address-keying bullet), add:

```markdown
  - `bsns_year`: the business-licence `folderyear` this build used, as a four-digit year (the City publishes two digits). Dataset-level — the same on every row. The export publishes it as `filter_config.licence_year` for the popup's licence provenance.
```

In the spec, change `Status:` to `implemented (plan: docs/superpowers/plans/2026-09-23-ownership-layers.md)`. Replace the `registry_filed` row with `registry_retrieved` and the description "Latest Samwise order date (date only) — when the registry record was retrieved, not a filing date". Change the registry tooltip example to end in `, record retrieved 2025-03-14`.

- [ ] **Step 3: Rebuild real data**

Run from the repo root:

```bash
uv run python scripts/prepare_data.py
uv run python scripts/export_pid_address_map.py
uv run python scripts/rebuild_data.py
```

Expected: each script completes. `buildings.csv` reports 5,152 rows. Ingest reports `buildings: 5141`.

- [ ] **Step 4: Spot-check the real export**

```bash
uv run python -c "
import json
d = json.load(open('data/derived/artifacts/building_records.json'))
r = next(r for r in d['records'].values() if r['address'] == '522 e 8th ave')
print({k: r[k] for k in ('owner_name','owner_source','licence_holder','network_name','network_source','network_buildings_on_map','network_properties_on_title','network_evidence')})
print(json.load(open('data/derived/artifacts/filter_config.json'))['licence_year'])
"
```

Expected: `owner_name` is `ST. GEORGE ESTATES LTD.`, `owner_source` is `registry`, `licence_holder` is `Willow Lane Apartments Inc`, `network_name` is `GLR PROPERTIES LTD.`, `network_source` is `claims`, `network_buildings_on_map` is 19, `network_properties_on_title` is 23, and `network_evidence.registry` > 0. `licence_year` prints `2026`.

- [ ] **Step 5: Full suites**

Run: `uv run pytest tests/ -q && (cd frontend && npx vitest run && npx tsc --noEmit -p .)`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/DATA_SOURCES.md docs/superpowers/specs/2026-09-23-ownership-layers-design.md
git commit -m "Document network labels, public ownership provenance, and the licence year"
```

- [ ] **Step 7: Manual check in the running dev server (report the results; this can't be automated)**

Refresh the browser tab against the running Vite dev server, then check:
- 522 E 8th Ave popup shows "ST. GEORGE ESTATES LTD.", "Licensed as Willow Lane Apartments Inc", "Part of the GLR PROPERTIES LTD. network" and "19 buildings on map · 23 properties on title · …".
- Each "i" icon shows its source on hover. At a narrow viewport (≤ 480 px), tapping the icon shows it too.
- The Buildings tab has Owner and Network columns, and Network is blank for single-name landlords.
- Landlords tab: Networks is the default. Owners switches the table. Row hover and selection highlight the right markers in both views. Reset clears both. The landlord search still filters.
