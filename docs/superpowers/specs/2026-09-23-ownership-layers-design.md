# Ownership layers: owner vs. network, with provenance

Date: 2026-09-23
Status: approved in conversation, awaiting written-spec review

## Problem

The public map flattens ownership into one label. `export.py` overwrites each
building's `owner_group`/`owner_key` with its claims-derived portfolio name
whenever one exists, and that single label drives the popup, the Buildings
and Landlords tables, search, and hover-highlight.

The data has distinct layers, and the flattening misattributes title. For 522
E 8th Ave:

| Layer | Value | Source |
|---|---|---|
| Licence holder | Willow Lane Apartments Inc | City business licence |
| Registered owner (LOTR reporting body) | ST. GEORGE ESTATES LTD. | BC Land Owner Transparency Registry, per PID |
| Network | GLR PROPERTIES LTD. | `resolve_owner_groups()` over confirmed `common_owner` claims |

The popup names GLR Properties as owner, but GLR is not on title for this
building. For 525 W 14th Ave the same label happens to be correct. Nothing on
the page tells the two cases apart, and nothing says where any ownership
statement comes from.

## Goals

1. Show the building's own owner and its network as separate facts.
2. Every ownership statement in the popup carries a provenance indicator
   (source on hover or tap).
3. Network display names default to today's rule and can be overridden
   through claims.
4. Show a network's size both as buildings on the map and as properties on
   title.
5. Fix nondeterministic network assignment for buildings whose PIDs reach
   more than one network.

## Non-goals

- Per-link provenance (which filing or claim connects which two entities).
  That needs a separate network artifact (see "Future: network artifact").
- A redesign of multi-owner display. Buildings keep one primary registered
  owner; the full list is exported for later use.
- `managed_by` and `same_entity` claims. They stay unused by the map.
- Buildings whose PIDs map only to a secondary address. This is a known
  limitation of the PID-to-`addr_key` bridge that already exists today.

## Decisions (from the design conversation)

- **Primary registered owner:** the reporting body holding the most of the
  building's PIDs, ties broken alphabetically. This mirrors how networks are
  named today. To be revisited.
- **Network naming:** the default stays "the entity holding the most PIDs".
  A new `network_label` claim can override it.
- **Network size:** show both counts, buildings on the map and properties on
  title.
- **Individual names:** LOTR interest holders and reporting bodies are public
  provincial registry data and are displayed as published. Owners can seek
  removal through official channels. This is recorded in CLAUDE.md's
  sensitivity section as a deliberate decision.
- **Public provenance:** the public artifact carries source *types* and
  counts only, never `source_note`. `tenant_report`, `manual_research` and
  any other non-registry type collapse to a single "VTU research" label, so
  the public map never signals that a tenant reported on a landlord. Full
  detail is reserved for the internal app.
- **Buildings tab:** shows both Owner and Network columns.

## Design

### 1. Export contract: building records

`owner_group`/`owner_key` stop being overwritten. Today's flattened value is
exactly the network view, so it moves to `network_*` unchanged, and a real
owner layer is added.

| Field | Meaning |
|---|---|
| `owner_name` | Primary LOTR reporting body for the building's PIDs; otherwise the licence holder (today's pre-overwrite `owner_group`) |
| `owner_key` | `sanitize_owner(owner_name)` |
| `owner_source` | `"registry"` or `"licence"` |
| `registered_owners` | All distinct reporting bodies for the building, primary first; `[]` if none |
| `registry_pids` | The building's PIDs that have a LOTR filing, dashed as filed |
| `registry_filed` | Latest `order_created_date` (date only) across those filings; null if none |
| `licence_holder` | The licence-holder label (today's pre-overwrite `owner_group`) |
| `network_key` | Claims cluster key if the building is in a confirmed cluster; otherwise today's licence `owner_key` |
| `network_name` | The cluster's display name; otherwise the licence holder label |
| `network_source` | `"claims"` or `"licence"` |
| `network_name_source` | `"default"` or `"claim"` (only meaningful when `network_source == "claims"`) |
| `network_entities` | Cluster entities (today's `portfolio_entities`); null for licence networks |
| `network_buildings_on_map` | Number of exported building records sharing `network_key` |
| `network_properties_on_title` | Distinct PID-mapped addresses reached by the cluster (today's `portfolio_building_count`); null for licence networks |
| `network_evidence` | `{"registry": n, "vtu_research": m}`: confirmed, active `common_owner` claims whose both entities are in the cluster, by collapsed source type; null for licence networks |

Removed: `owner_group`, `portfolio_name`, `portfolio_building_count`,
`portfolio_entities`.

`owner_key` keeps its name but changes meaning, from network to owner. Every
consumer is updated in the same change (listed under "Touch points"), so no
reader silently keeps the old semantics.

Overlay-only records (unmatched co-ops and SROs) have no PIDs and no licence.
They get `owner_name`/`network_name` `"(Unknown)"`, keys `"unknown"`, sources
`"licence"`, and null counts, which is how they are handled today.

`network_key` for a claims cluster is `sanitize_owner(default name)`. It is
independent of any `network_label` override, so relabelling a network never
changes its key.

### 2. Export contract: other artifacts

- `marker_metadata.json`: each marker gains `network_key`. `owner_key` now
  carries the owner key.
- `filter_config.json`: gains `licence_year`, the business-licence
  `folderyear` the export was built from, as a four-digit year.
  `prepare/buildings.py` already selects the latest `folderyear`, which the
  source publishes as two digits ("26"). It writes that value as a
  four-digit `bsns_year` column (2026) in `buildings.csv`. `raw_buildings`
  stores it verbatim, a new column in `RAW_BUILDINGS_COLUMNS` and
  `schema.sql`, and the export reads `MAX(bsns_year)`.
- `BUILDING_RECORD_COLUMNS`, the explicit public column list, is updated to
  the fields above. It remains the single gate on what reaches the public
  artifact.

### 3. Registered owners (backend)

`metrics/portfolios.py` already loads `pid_address_map.csv` and
`raw_lotr_ownership`. It gains a function that returns, per `addr_key`, the
reporting bodies with their PID counts, the filed PIDs, and the latest
filing date. The owner is chosen by most PIDs, then alphabetically. Reporting
bodies are compared by `sanitize_owner()`, and the displayed spelling is the
most frequent raw spelling for that key.

Contested buildings: if a building's reporting bodies fall in more than one
cluster, the building goes to the cluster that holds the most of its PIDs,
then the larger cluster (by properties on title), then the cluster key
alphabetically. This replaces the current behaviour, where the
last-processed cluster wins.

### 4. Network display names via claims

- New relationship value: `network_label`. `entity_a` is any entity in the
  network, and `entity_b` is the display label as free text. It is written
  through `record_claim()` like any other claim, and follows the same
  confidence gate and retraction rules.
- Resolution: among confirmed, active `network_label` claims whose
  `entity_a` is in the cluster, the most recent `updated_at` wins. If there
  are none, the default name applies. Claims whose `entity_a` is not in any
  cluster are ignored.
- `entity_b` of a `network_label` claim is not an entity:
  - `record_claim()` applies only whitespace cleanup to it. It skips
    `clean_owner_label()` and the `find_similar_entity()` collapse, so the
    label is stored exactly as written.
  - `list_known_entities()` and `find_similar_entity()` exclude it, so labels
    never appear in entity autocomplete or duplicate warnings. The bulk
    importer's similar-entity warning skips it for the same reason.
- No schema change is needed. `relationship` is already free text.

### 5. Provenance indicators (popup)

Each ownership line in the popup ends in a small icon. Its tooltip text, all
of which is escaped:

- **Owner, registry:** "BC Land Owner Transparency Registry: PID 008-173-613
  (+N more), latest filing 2025-03-14". Up to three PIDs are listed.
- **Owner or licence line, licence:** "City of Vancouver business licence,
  {licence_year}".
- **Network, claims:** "Grouped from {registry} provincial registry filings
  and {vtu_research} VTU research claims". A part is omitted when its count is
  0. A second sentence follows: "Name: default (entity with the most
  properties)" or "Name: set by claim".
- **Network, licence:** "Grouped by business licence name".

The icon is a focusable element (`tabindex="0"`) that carries the same text
in `aria-label`. A pure-CSS tooltip shows on `:hover` and `:focus`, so tapping
it on a phone shows the text. No JavaScript is added inside popup HTML.

### 6. Popup layout

```
ST. GEORGE ESTATES LTD. ⓘ              +1 co-owner, when registered_owners > 1
Licensed as Willow Lane Apartments Inc ⓘ   only when licence_holder differs from owner_name
Part of the GLR PROPERTIES LTD. network ⓘ
19 buildings on map · 23 properties on title · 19 linked entities
```

The network lines appear when `network_source == "claims"`, or when
`network_buildings_on_map > 1`. For a licence network only the on-map count
is shown.

### 7. Tables

- **Buildings tab:** the Landlord column is replaced by **Owner** and
  **Network**. The Network cell is blank when `network_name == owner_name`.
  Rows carry `data-owner` (owner key) and a new `data-network` (network key).
  Row search text includes both names.
- **Landlords tab:** an **Owners | Networks** toggle switches between two
  tables. `#owners-table` aggregates by `owner_key`, and `#networks-table`
  aggregates by `network_key`, which equals today's Landlords table. Each
  keeps its own totals row. Networks is the default view, so the tab looks
  unchanged on first load.
- Row types: owner rows are `data-type="owner"`, network rows are
  `data-type="network"`.

### 8. `wiring.js`

- Build `window.networkIndex` from `meta.network_key` beside the existing
  `ownerIndex`.
- Add `setNetworkSelection` and `networkHover`, mirroring `setOwnerSelection`
  and `ownerHover`. The row-select handler routes `network`.
- Hover listeners, `cacheRowCells`, row visibility in `applyFilters`, group
  table summaries and Reset cover both landlord tables.
- Selections in the two views are independent and persist across toggling.
- The landlord search matches building rows on either name, through the
  existing `data-search`.

## Touch points

- **Backend:** `metrics/portfolios.py`, `claims.py`, `export.py`,
  `ingest/ownership_claims.py` (warning skip), `prepare/buildings.py`,
  `ingest/raw_buildings.py`, `schema.sql`, `scripts/make_frontend_fixtures.py`
- **Frontend:** `types.ts`, `popup.ts`, `popup.css`, `tables.ts`,
  `index.html`, `wiring.js`, `frontend/fixtures/*`
- **Docs:** CLAUDE.md, covering the `network_label` convention in "Claims
  ingestion & entity resolution", the public-provenance and individual-name
  decisions in "Sensitivity model", and a Phase 1 note. Also
  `docs/DATA_SOURCES.md`, for the `bsns_year` column.

## Testing

Following CLAUDE.md's targeted-test policy, claims logic and the public field
filter get automated tests.

**pytest**
- `network_label` resolution: default name with no label, a confirmed label
  overrides it, retracted and unconfirmed labels are ignored, the latest of
  several wins, and a label on an entity outside any cluster is ignored.
- `record_claim()` stores `network_label` text verbatim.
  `list_known_entities()` and `find_similar_entity()` never return a label.
- Registered owner: most-PIDs selection, alphabetical tie-break, fallback to
  licence with `owner_source == "licence"`, and date and PID fields.
- Contested building tie-break is deterministic, and independent of claim
  insertion order.
- `network_evidence` collapses every non-registry `source_type` into
  `vtu_research`. No `source_note` text reaches any artifact: seed a
  distinctive note and assert it appears nowhere in the output files.
- `BUILDING_RECORD_COLUMNS` matches the new public list.
- Both network counts, including a network whose properties on title exceed
  its buildings on the map.

**vitest**
- Popup: owner and network lines, co-owner suffix, licence line shown only
  when it differs, provenance text for each source, and all interpolated
  values escaped.
- Tables: Owner and Network columns with a blank network cell,
  `data-network`, owners and networks aggregation.

**Manual:** in the dev server, check that 522 E 8th Ave shows ST. GEORGE
ESTATES LTD. as owner within the GLR network, that tooltips work on hover and
on tap (narrow viewport), and that toggle, selection and hover work in both
Landlords views.

## Future: network artifact (option C)

A separate `networks.json` keyed by `network_key` would carry each entity's
role (reporting body, interest holder, licence holder) and per-link
provenance. It builds on the stable `network_key` introduced here without
reshaping building records.
