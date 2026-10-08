# Building popup redesign and export contract v2

Date: 2026-10-08
Status: design approved in conversation; awaiting spec review

## Problem

The building popup is assembled from a flat ~60-column record
(`export.py::BUILDING_RECORD_COLUMNS`). Ownership alone spreads over ~20
columns from four sources (`owner_*`, `registered_owners`, `registry_*`,
`licence_holder`, `managed_by*`, `listings`, `network_*`) and the SRO overlay
repeats part of it (`sro_owner`, `sro_operator`). A single precedence-picked
"owner" slot blurs who holds title, who the City licenses, and who runs the
building, so `popup.ts::ownershipLines()` reconstructs the story with a tangle
of special cases. Concretely wrong today: 518 Richards St (Marble Arch) shows
PHS Community Services Society as *owner*; the SRO inventory says BC Housing
owns it, Atira manages it, and PHS only holds the licence.

The record also carries sentinels (`"(Unknown)"` on 2,342 owners and 2,586
licence holders, `"unknown"` keys, `""` on building rows' overlay fields),
loose types (`year_built` float, `sro_registered_rooms` string, raw codes like
`open_waitlist`), PDF-extraction damage in SRO text, and exported data the
popup never shows (rezoning, land/building ratio, SRO sectors).

## Goals

1. Model ownership as **parties in roles**, each with its own sources and dates,
   instead of one precedence-picked owner.
2. Separate **who owns** (network → on-title owner) from **who runs it day to
   day** (manager) — the ownership/accountability split.
3. A typed, validated export contract: real nulls, real types, no sentinels,
   shared by Python and TypeScript.
4. A concise, tabbed popup that answers a tenant's questions first (Summary),
   gives organizers the ownership chain (Ownership), and surfaces building
   context including redevelopment pressure (Building).
5. Portfolio-level accountability: network totals of buildings, units and open
   City issues.

Audience priority: tenants looking up their building and organizers/researchers
first; experts and funders should be able to see the depth (evidence tiers,
provenance, portfolio) without it crowding the tenant view.

## Non-goals

- **Entity kinds/sectors** (company / individual / nominee / non-profit /
  government). The contract reserves a nullable `kind` slot; populating it is a
  separate project that resumes the paused sector classification
  (`metrics/sector.py`, City-owned properties dataset).
- A parcel-level building model. `prepare/buildings.py::collapse_parcels()`
  stays as is for values and physical attributes; only ownership becomes
  per-parcel (per-party PIDs).
- Unconfirmed networks in public output.
- Rewriting pipeline-internal grouping that relies on `owner_key == "unknown"`
  (`merge.py`, `normalize.py`, `listing_buildings.py`). Sentinels are removed
  at the export boundary.
- Deployment. Nothing here publishes; the sensitivity gate is re-checked
  immediately before any later publish.

## Background: how others model this

Brief record of the research that shaped the role model.

- **Registries with typed contacts** (NYC HPD registrations, Toronto
  RentSafeTO): a building has contacts by role (owner, officer, agent, site
  manager). JustFix's *Who Owns What* is built on this. Toronto registers only
  a primary contact; tenant groups there are still asking for owner names.
- **Inferred networks, flagged as inferred** (Who Owns What, Milwaukee's
  MKEPropertyOwnership, Evictorbook): name/address matching and shared
  tax-mailing addresses. Authors stress that linked LLCs are legally distinct
  and common ownership often can't be proven. Our claims-based networks rest on
  stronger evidence (registry filings + VTU research), which is worth showing.
- **Statements as sourced claims** (Open Ownership's BODS, LittleSis): every
  link is a dated assertion by a source; direct vs indirect interests are
  distinct; absence is recorded explicitly ("no beneficial owners"), not left
  blank.
- **Portfolio-level accountability** (Milwaukee, Who Owns What): violations and
  evictions shown across a landlord's whole network.
- **Tech Tools for Justice, *Landlord Data Methodology* (Pederson, 2025)**:
  distinguishes Landlord Networks (true-owner proxy), Landlord Organizations
  (property managers etc. — accountable for conditions though not necessarily
  owners) and Landlord Entities (law firms, registered agents — neither).
  Classifies entity kinds separately from roles; excludes intermediary
  addresses and common names from network linking; publishes networks at
  several strictness levels.

Data checks behind the role decisions:

- Operator vs manager is not a public/private split. In the SRO inventory,
  sectors vary independently of role (e.g. 10 privately owned SROs have
  non-profit operators, mostly Atira); only 12 of 65 operators are the owner.
  "Operator" is the SRO inventory's word for the manager role.
- The licence holder is a source, not a role. Of 463 buildings with both a
  registry owner and a licence holder, ~70% are the owner under another
  spelling; the rest are related companies (VLC Leaseholds / Concert
  Properties), non-profit operators (Urban Vision Housing Society; PHS on BC
  Housing SROs), or managers (Dorset).
- 51 buildings have more than one registered owner, mostly joint owners of a
  single PID; only 27 span several PIDs.

## Design

### 1. Roles

| Role | Meaning | Sources, in precedence order |
|---|---|---|
| `owner` | Holds title | LOTR reporting body; SRO inventory owner; business licence (fallback) |
| `interest_holder` | Behind the owner | LOTR interest holders, trustees, settlors, partners |
| `manager` | Runs the building day to day | Listings; `managed_by` claims; SRO inventory operator |
| `licensee` | The City's landlord of record | Long-term rental business licence |

`network` is not a role: it groups entities, carried in `networks.json`.

### 2. Export contract v2

Defined as Pydantic models in a new `tc_core/contract.py`, every model with
`extra="forbid"` so the public field set is an explicit allowlist. Records are
validated as they are written; a validation failure fails the export.

`schema_version` becomes `2` on every artifact.

**Files**

- `building_records.json` — new shape below.
- `networks.json` — new; one entry per network, referenced by
  `Building.network_id`.
- `marker_metadata.json` — keeps its flat fields (`owner_key`, `network_key`,
  …) as the map's fast path; adopts real nulls only.
- `filter_config.json` — gains `land_share_median`.
- `contract.schema.json` — the JSON Schema emitted from the models; committed.

**Models**

```text
Building
  id: int
  origin: "building" | "overlay_sro" | "overlay_coop"   # today's `source`
  address: str
  name: str | null
  also_known_as: [str]
  local_area: str | null
  block_id: int | null
  lat, lon: float | null
  in_chinatown, in_village_plan: bool
  units: int | null
  units_basis: "inventory" | "licence_fee" | "sro_rooms" | null
  year_built: int | null
  listed_in: [SourceType]
  value: Value | null
  issues: Issues | null
  parties: [Party]
  network_id: str | null
  registry_search: RegistrySearch
  coop: Coop | null
  sro: Sro | null
  rezoning: Rezoning | null

Party
  role: "owner" | "interest_holder" | "manager" | "licensee"
  name: str
  entity_key: str
  kind: null                       # reserved; populated by the sector project
  interest: str | null             # interest_holder only, e.g. "interest holder", "trustee", "settlor", "partner"
  pids: [str]                      # owner / interest_holder only
  same_as: "owner" | "manager" | null   # licensee only
  sources: [Source]

Source
  type: SourceType
  as_of: date | null
  url: str | null                  # http(s) only; listings

SourceType = "registry" | "licence" | "sro_inventory" | "listing"
           | "claim_registry" | "vtu_research"
           | "rental_inventory" | "non_market_list" | "chf_bc" | "rezoning"

Value
  land: int
  building: int
  land_share: float                # land / (land + building)
  land_share_pctl: int             # 0–100

Issues
  count: int
  url: str | null

RegistrySearch
  status: "filed" | "no_filing" | "not_searched"
  date: date | null

Coop
  status: "open_waitlist" | "closed"
  ownership_model: "non_profit" | "equity"
  url: str | null

Sro
  rooms: int | null
  occupancy: "open" | "closed" | null
  owner_sector: Sector | null
  operator_sector: Sector | null

Sector = "private" | "non_profit" | "government" | "chinese_society"

Rezoning
  status: "approved" | "rezoning" | "upcoming"
  category: str                    # e.g. "approved_market"
  detail: str | null               # e.g. "Approved March 13, 2025"
  url: str | null

Network
  id: str
  name: str
  name_source: "claim" | "default"
  tier: "confirmed" | "name_match"
  evidence: { registry: int, vtu_research: int }
  entities: [str]
  totals: { buildings: int, units: int, open_issues: int, properties_on_title: int | null }
```

Enum values are emitted as codes; the frontend owns one label map.

**Validation rules (contract-wide)**

- Every string field rejects `"(Unknown)"`, `"unknown"`, `""` and
  whitespace-only values.
- Unknown fields are rejected (`extra="forbid"`).
- Dates are ISO `YYYY-MM-DD`.

### 3. Assembling parties (`tc_core/export_parties.py`)

All resolution happens in Python; the frontend only renders.

- **owner** — one party per LOTR reporting body on the building's PIDs, with
  the PIDs it holds. Ordered by the existing primary-owner rule (most PIDs,
  then alphabetical). Without a filing: the SRO inventory owner. Without that:
  the licence holder, unless the licence holder is a known manager (confirmed
  `managed_by` claim), as today.
- **interest_holder** — `raw_lotr_ownership` rows for the building's PIDs whose
  `type_of_interest` is not the reporting body itself (`INTEREST_HOLDER`,
  `RB_TRUSTEE_*`, `RB_TRUST_SETTLOR_*`, `RB_PARTNER_*`), mapped to a readable
  `interest`. Name and interest type only. Residence, citizenship and
  registered-address fields are never read into the model.
- **manager** — listings, confirmed `managed_by` claims, SRO operator. Parties
  with the same `entity_key` merge into one with several sources.
- **licensee** — present whenever a licence exists. `same_as` is `"owner"` or
  `"manager"` when its entity matches that party by normalized key
  (`clean_owner_label`/`sanitize_owner`) or by a confirmed `same_entity`
  cluster (`claims.py::resolve_entity_clusters`); otherwise `null`.
- **SRO precedence change** — for SROs the inventory's owner now outranks the
  licence (Marble Arch: owner BC Housing, manager Atira, licensee PHS with
  `same_as: null`). `export.py::fill_owner_from_sro` changes accordingly: the
  SRO owner replaces a licence-sourced owner, and a licence-name network
  becomes the SRO owner's name group (so BC Housing's SROs group together).
  Registry owners and claims networks are never replaced.

**Provenance stays public-safe.** `Source.type` carries only types; every
non-registry claim source collapses to `vtu_research`; `source_note` never
leaves the database (CLAUDE.md sensitivity model, unchanged).

### 4. Derived values

- **Network totals** — buildings and units on the map, open City issues
  (sum of `n_issues`), properties on title (claims networks only, else null).
- **Land share** — `land / (land + building)` for buildings with both values
  and a positive total. `land_share_pctl` = share of those buildings with a
  strictly lower land share, as a whole percent. `land_share_median` goes to
  `filter_config.json`. (Current data: 4,786 buildings, median 79%; 39% of
  buildings are at ≥ 90%, so a fixed "high pressure" threshold would over-label.)
- **Network tier** — `confirmed` for claims networks; `name_match` for every
  other grouping (same licence-holder name, same SRO-inventory owner, or an
  owner on its own). Every building with an owner has a `network_id`, so the
  tables can always group; the popup shows a network as such only when it is
  `confirmed` or covers more than one building.
- **Registry search** — `filed` if any LOTR owner; `no_filing` with its date
  when a search found nothing (today's `registry_no_filing`); else
  `not_searched`.

### 5. Cleaning

- **Sentinels** — removed at the export layer (`export.py`) and from the
  frontend (`tables.ts`, tests). Pipeline internals keep theirs (non-goal).
- **Types** — `year_built`, `units`, SRO rooms → int; assessed values → int
  dollars (`value_bldg = 1` is a valid value); dates → ISO strings.
- **SRO text** — the inventory came from a PDF. Cleaning is a pure module
  (`tc_core/sro_text.py`) applied at export, next to the existing
  `export.py::clean_sro_name`; `raw_sro` and `overlay_housing` keep the source
  text, so a cleaning change never needs a re-ingest.
  1. Split words in sector fields (`"N on-Profit"`, `"P rivate"`) →
     normalized to `Sector`.
  2. Sector labels leaked into operator names (`operator = "Private"`,
     `"vP rivate"`, `"SPrivate"`, `"nPrivate"`) → operator `null` when the name
     is only a leaked label; the sector survives in its own field.
  3. Truncated names (`"Atira Women's Resourc"`,
     `"Vancouver Chinatown Foundation For Communty R"`) → expanded via the
     existing `export.py::SRO_NAME_ALIASES`. Implementation produces the list
     of truncated names for the user to supply full names.

### 6. Popup

Split `popup.ts` into `frontend/src/popup/`:

- `index.ts` — shared header and tab switching.
- `summary.ts`, `ownership.ts`, `building.ts` — one per tab.
- `labels.ts` — enum → display text.

**Header (all tabs)** — address; name · local area · units (or rooms) · built
year.

**Tabs** — buttons with `role="tab"`, arrow-key navigation. The last-opened tab
is remembered in memory for the page session (no storage; resets to Summary on
reload), so an organizer
clicking through buildings stays on Ownership.

**Summary** (tenant view)

- Housing badges when they apply: SRO (+ occupancy), Co-op.
- *Owned by* — the network name if its tier is `confirmed`; else the primary
  owner, with a "licence only" tier label when the licence is its only source;
  else "Not on record". Evidence tier label + ⓘ.
- *Managed by* — the manager (listing link if any), else "Not on record".
- *Licensed to* — only when the licensee has `same_as: null`.
- Portfolio line when the network covers more than one building
  ("Cressey holds 10 buildings · 609 units on the map"); "Only building we know
  of for this owner" otherwise.
- City issues count with link.
- Rezoning alert (approved or open rezoning): status, date, Shape Your City
  link.

**Ownership** (organizer view) — a vertical chain:

1. **Network** — name, tier, "N registry filings + M VTU research claims",
   portfolio card (buildings · units · open issues), linked entities collapsed.
2. **On title** — owner(s) with PIDs and registry date. Joint owners of the
   same PID read "jointly owned by A and B"; owners of different PIDs are
   listed per parcel. "Licensed as X" sub-line when the licensee has
   `same_as: "owner"` and its name differs textually. Interest holders
   collapsed ("▸ 3 interest holders"), each with its interest type.
   "No filing in the land title registry (searched DATE)" when
   `registry_search.status == "no_filing"`.
3. **This building** — chain terminus.

Below a dashed rule, outside the chain: **Manages** — manager with source and
date ("company website, seen Sep 2026"); "Licensed as X" sub-line when the
licensee has `same_as: "manager"` and differs textually.

**Building**

- Assessed value: a bar filled with the land share, a subtle 1px tick at the
  city median labelled "city median" beneath it, "Land $X (N%) · Building $Y"
  with ⓘ explaining land share as a redevelopment-pressure signal, and "Land
  share higher than P% of rental buildings on the map".
- Rezoning section (status, type, details link) when present.
- SRO section (rooms, status, owner/operator sectors) when present.
- Co-op section (model, waitlist, CHF BC link) when present.
- City issues; "Also known as".
- *Records* — "Listed in …" from `listed_in`, with ⓘ.

Collapsed lists use native `<details>`/`<summary>`. Provenance icons reuse
`provenance.ts`, now fed from `Party.sources`. Popup width stays ≤ 300px;
Leaflet `autoPan` handles height.

Mockups from the design session are in `.superpowers/brainstorm/` (local,
untracked).

### 7. Other frontend consumers

- `types.ts` keeps frontend-only types; artifact types come from
  `src/contract.gen.ts`, generated from `contract.schema.json` by
  `npm run gen:types` (`json-schema-to-typescript`, dev dependency).
- `data.ts` loads `networks.json`.
- `tables.ts` (Buildings and Landlords tables), `landlord-picker.ts`,
  `wiring/indexes.ts`, `coverage.ts`, `wiring/status-export.ts` read the flat
  view (section 8); their sentinel checks go.
- `markers.ts` unchanged apart from nulls.

### 8. Flat view for tables and CSV

The sidebar tables, landlord picker, map indexes, coverage panel and the
"export visible buildings" CSV are flat by nature (the CSV writes record
columns verbatim). Rather than teach each one the nested shape, `data.ts`
derives a flat view model per building (`frontend/src/flat.ts::flatten`) with
the fields they read today — `owner_key`, `owner_name`, `owner_source`,
`network_key`, `network_name`, `network_source`, `managed_by`, `housing_type`,
`value_land`, `value_bldg`, `bldg_land_ratio`, `registry_no_filing`, … — with
nulls in place of sentinels. `BuildingData.columns` becomes the flat column
list, so the CSV keeps one plain column per field and never contains nested
JSON. The popup reads the nested `Building` directly. The consumers drop their
`"unknown"` checks; the tables keep "unknown" only as their own UI group key
for "Not on record" rows.

### 9. Dependencies

- Python runtime: `pydantic` (v2).
- Frontend dev: `json-schema-to-typescript`.

## Testing

Targeted per CLAUDE.md §6, sensitivity and claims logic first.

**Python**

- Sensitivity canaries (extend `tests/test_export_ownership.py`): no LOTR
  residence/citizenship/registered-address value appears in any artifact;
  `source_note` never appears; non-registry claim sources appear only as
  `vtu_research`; unconfirmed networks never appear.
- Contract: sentinel strings rejected; unknown fields rejected; committed
  `contract.schema.json` equals the schema generated from the models.
- Party assembly fixtures from real cases: licensee spelled differently from
  owner → `same_as: "owner"` (2145 York Ave); SRO owner outranks licence,
  licensee unmatched (518 Richards St); manager holds the licence →
  `same_as: "manager"`, no fallback owner (Dorset); joint owners of one PID vs
  owners of separate PIDs; interest holders typed trustee/settlor.
- SRO cleaning: split words, leaked labels, alias expansion.
- Derived values: land-share percentile and median, network totals, registry
  search status.

**Frontend (vitest)**

- Each tab renders for four fixtures: rich private (2145 York Ave), SRO
  (518 Richards St), rezoning (396 E 2nd Ave), sparse licence-only
  (1255 Bidwell St).
- `"(Unknown)"` never renders; all values HTML-escaped (existing XSS tests
  carried over); non-http(s) URLs never linked.
- Tab keyboard navigation; tab memory; `<details>` collapsed by default.
- Fixtures regenerated via `scripts/make_frontend_fixtures.py`.

## Rollout

- One branch; export and frontend move to `schema_version: 2` together. No
  dual v1/v2 support.
- No deploy as part of this work.
- Docs:
  - CLAUDE.md sensitivity section: interest holders are published with name
    and interest type only; residence, citizenship and addresses are not.
  - CLAUDE.md open question on multi-parcel buildings: ownership half resolved
    (per-party PIDs); values/attributes half stays open.
  - `docs/DATA_SOURCES.md`: SRO text cleaning.

## Open items for implementation

- Full names for truncated SRO owner/operator names (list produced during
  implementation; user supplies).
- Exact ⓘ wording for land share and evidence tiers (draft during
  implementation; user reviews).
