# Tenant Commons v2 — Spec & Roadmap

*Living document. Update this as decisions change — it's meant to be edited, not archived.*

Last updated: 2026-10-20

---

## 1. Purpose & vision

Tenant Commons is a **prototype data project**, using Vancouver and VTU (Vancouver Tenants Union) as the case to explore whether — and how — it's worth building out. It has two uses, equally weighted:

1. **A public tool for tenants** — the map at map.tenantcommons.ca: who owns, manages and licenses a building, and which landlord network it belongs to.
2. **An internal tool for organizers** — combining public property/rental data with VTU's own data and manually-researched ownership knowledge gathered from tenants (e.g. "these two shell companies are secretly the same landlord"). Requirements still open — see Section 4.

**The long-term interest is data infrastructure.** The aim is political: bridging the power and information gaps between landlords and tenants. That means modeling ownership and control properly (see "Ownership modeling direction" in Section 3), not just drawing it on a map.

The manually-curated ownership knowledge — built from tenant testimony and research — is what nobody else has, and what tools like WhoOwnsWhat or the Anti-Eviction Mapping Project don't do. The architecture below is built to protect and grow that asset first.

**Not current goals** (don't design for them or bring them up as drivers): funding is an open question still being explored, not a design target; Toronto and other collaborators are interesting, but no other municipality or location gets explored without funding.

---

## 2. Product & org scope

| Decision | Answer | Rationale |
|---|---|---|
| Public vs. internal | **Both**, as separate views/products (Q1) | The public map must never expose VTU membership or tenant-identifying details (a landlord can find the site). Public map = transparency layer for tenants; internal tool = organizer utility. |
| Single-org vs. multi-tenant | **Vancouver/VTU only** (Q2, revised 2026-10-20) | No other locations without funding. Keep city/region a first-class field and avoid Vancouver-only assumptions where it costs nothing, but don't build for generalization. |
| Geographic scope | **No hard-coded geographic restriction in the data layer** — ingest/merge pulls whatever the source data covers (Q3, revised 2026-08-06) | Which buildings to *ingest* and which to *research deeply* are different questions. Only research depth needs to stay narrow; restricting ingestion adds filtering work for no benefit. |

---

## 3. Data model & pipeline (`tc_core`)

### Known data sources (Q4)
- **Vancouver Open Data platform** — addresses, shapefiles/boundary files, rental business licences.
- **City of Vancouver FOI records** — purpose-built rental inventory (address, year built, size, name). Periodic, public.
- **VTU NationBuilder exports** — membership data. **Removed from the pipeline 2026-10-20:** nothing public used it, and keeping it out means the database behind the public map holds no membership data at all. If an internal tool needs it (Section 4), it gets its own store, joined by address.
- **Manual research / tenant reports** — common ownership across shell companies, identified through tenant testimony. Grows piecemeal, no external source — this is the project's core IP.
- **Third-party online sources** — e.g. CHF BC's co-op housing list. Scraped/pulled from another organization's own site, not the City or VTU.

The on-disk layout (`raw/` → `curated/` → `derived/`) and rebuild order are described in [`data/README.md`](data/README.md); everything under `data/` except the README and per-source manifests is gitignored.

See [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) for the full per-source catalog: origin, license/attribution, fetch method (scripted vs. manual), format quirks, and refresh cadence for every source above except manual research (which lives entirely in the `ownership_claims` model below).

### Storage engine (Q6)
**SQLite now, schema designed to be Postgres-compatible.** No infrastructure to run/pay for/secure while solo and pre-funding. Migrating to Postgres later (multi-user concurrency, hosted internal app) should be mechanical, not a rewrite — avoid SQLite-specific schema quirks.

### Claims model (Q5, elaborated)
The manually-curated layer (starting with **ownership claims**) is modeled as its own first-class, auditable table — **not** folded into the same table as scraped/open data. This protects hard-won manual research from being silently overwritten by data re-imports, and gives every assertion a traceable source.

**`ownership_claims` table (v1 scope):**

| field | purpose |
|---|---|
| `claim_id` | stable identifier |
| `claim_key` | stable idempotency key, human-authored (bulk-CSV import) or auto-generated (form/programmatic entry) — see "Claims ingestion" below |
| `entity_a`, `entity_b` | the two entities linked (e.g. landlord names/IDs) |
| `relationship` | e.g. `common_owner`, `same_entity` |
| `source_type` | e.g. `tenant_report`, `manual_research`, `public_registry` |
| `source_note` | free text — who said what, context |
| `reported_by` | organizer identifier |
| `date_reported` | timestamp |
| `confidence` | e.g. `unconfirmed` / `confirmed` |
| `status` | `active` / `retracted` — claims are never deleted, only retracted, preserving history |

Built with an eye toward generalizing to a broader `claims` pattern later (see "Ownership modeling direction" below) (building condition reports, renoviction incidents, organizing-campaign stage, rent-increase reports, tenant willingness-to-organize signals, corrections to public data) — **not built now**, but the schema shape (entity + relationship/attribute + value + source + confidence + status + timestamp) should stay compatible with that future.

### Claims ingestion & entity resolution

**Entry paths.** Two, sharing one write function (`tc_core/claims.py::record_claim()`) so there's one implementation of the upsert/normalization logic, not two:

1. **Bulk-CSV import** (`tc_core/ingest/ownership_claims.py`) — for populating claims already gathered while researching (a spreadsheet you edit over time), not built for one-off entry. Each row requires a human-authored `claim_key`; import is an upsert by that key (existing key → update in place, bumping `updated_at`; new key → insert). Safe to re-run repeatedly against an evolving spreadsheet without duplicating rows. Retraction is just editing a row's `status`/`retracted_reason` and re-importing — never a delete. Run it standalone via `uv run python scripts/update_claims.py` — faster than the full pipeline since it touches only `ownership_claims`, not buildings/addresses/blocks/membership (still logs to `ingest_runs` like any other source). Assumes the database's already been initialized once via the full pipeline.
2. **Single-record form** (Internal app, Phase 1 — not yet built) — for the much-more-common small-scale case: a tenant names a landlord, a numbered company's real owner gets identified. Calls the same `record_claim()`; `claim_key` auto-generates (a UUID) since there's no spreadsheet to hand-author one in.

**Entity resolution — no canonical-entities/alias table.** Two different problems, handled differently:

- *Trivial spelling/formatting noise* (case, stray whitespace, list-like string artifacts) — collapsed automatically by `record_claim()` via the existing `clean_owner_label()` normalizer, before storage.
- *Genuine entity resolution* (a numbered company turns out to be a named person; two different-looking names turn out to be the same legal entity; two distinct entities share a beneficial owner) — recorded as a claim, not merged at the schema level. This is literally what the claims model is for (see Section 1's example). Relationship-value convention to keep the two cases distinguishable downstream (e.g. for future map clustering): `same_entity` = literally the same legal entity, just written differently; `common_owner` = different entities, same real owner.
- `claims.py::find_similar_entity()` gives a soft nudge (not a hard merge) when a new entity's normalized key matches an existing one under a different display spelling — used by the bulk importer as a warning, and intended for future form autocomplete.
- `claims.py::resolve_entity_clusters()` computes, at read time (no persisted table — see the design discussion this came from), a joined display name for every entity in a `same_entity` cluster (transitive — A~B, B~C joins all three), e.g. `"0733603 BC Ltd" -> "0733603 BC Ltd / Phil Kim"`. `display_name_for()` looks up a single entity against that result, falling back to the raw name. `claims.py::resolve_owner_groups()` does the equivalent for `common_owner`, but returns each entity's *group* (the other entities sharing its real owner) rather than joining names — these are legally distinct entities, so callers should present them as a portfolio/group (this is the `resolve_owner_groups()` behind CLAUDE.md's planned public-map "claims-derived landlord clustering," Section 5 Phase 1), not rename them. Both default to `confirmed`-only claims (`include_unconfirmed=True` opts into the softer behavior), matching the confidence gate above.
- `network_label` claims name a landlord network: `entity_a` is any entity in a `common_owner` cluster, `entity_b` the display label — free text, stored verbatim, and excluded from `list_known_entities()`/`find_similar_entity()`. The most recently updated confirmed, active label on any entity in the cluster wins; without one the network is named after the entity holding the most PIDs. Relabelling never changes a network's key.
- `entity_kind` and `institutional` claims are claims *about one entity*: `entity_a` is the entity, `entity_b` a value from a fixed vocabulary (`claims.ENTITY_KINDS`, `claims.INSTITUTIONAL_KINDS`), validated by `record_claim()` and, like labels, never an entity. `entity_kind` corrects the classifier's name rules; `institutional` (REIT, pension fund, insurer, asset manager) is claims-only. Latest confirmed, active claim wins (`claims.entity_attribute_claims()`). The first attribute-style claims, a small step toward the broader `claims` shape.

### Building classification (2026-10-20)

Every owner entity gets a kind (government / non-profit / co-op / individual / company / numbered company / trust / partnership) and every building an owner type, market status, operator type and scale (`metrics/sector.py`): from `entity_kind` claims, the registry's individual-or-corporation record, name rules, the City-owned properties list (`raw_city_owned_properties`, joined on a folio's land coordinate), and the co-op, SRO and non-market lists. The rental licence holder is a weaker signal, never the owner: anything not from title, a claim or City land is published as *inferred* with its basis. Nothing known is null. Exported in contract v5 (`Party.kind`, `Building.classification`, `NetworkTotals.assessed_value`); research CSVs via `uv run python scripts/classification_report.py`. See docs/superpowers/specs/2026-10-20-building-classification-design.md.

### Ownership modeling direction (2026-10-20)

The direction is a **BODS-like model** ([Beneficial Ownership Data Standard](https://standard.openownership.org/)): statements about entities, persons, and the ownership/control relationships between them, each with its own source and date. BODS hasn't worked out land and real estate as an asset; exploring that gap is the project's long-term interest — see Open Ownership's [Bridging the gap for effective asset transparency](https://www.openownership.org/en/publications/bridging-the-gap-for-effective-asset-transparency/). Vancouver has the ingredients: land title / LOTR interest holders, the City's SRO inventory naming who's behind a company, managers and licensees, and VTU research linking shell companies.

The current `ownership_claims` model and the export contract's parties-in-roles are working sketches toward this, not the final shape. Not a commitment to adopt BODS wholesale or now — a direction to keep new modeling compatible with.

**RTB decisions** are being ingested in a separate project. It stays separate for now (different demands and legal frameworks); the data models should converge eventually, but nothing here depends on it.

### Ingest run tracking

Every `run_ingest()` invocation gets a shared `run_id`; each source call is wrapped so it writes one row to `ingest_runs` (success with a row count, or failure with a full traceback) before a failure is allowed to keep propagating — this doesn't change the existing fail-fast behavior (a failing source still aborts the rest of the run), it just leaves a persistent record of what happened. `ingest_runs` is flat (one row per source per run) and never dropped, same persistence invariant as `ownership_claims`. No dedicated status CLI/command — query it directly via `sqlite3` for now, or browse it in the Internal app once that exists, same as any other table.

### Lineage hook (Q8c)
Full data lineage tracking (tracing every derived value back to its exact source rows and transform step) is a real, valuable data-engineering capability — but a separate future project, not built now.

**What *is* built now (~1 hour of work):** every row in every table (raw and merged) gets a stable, permanent ID, and the build pipeline writes a `source_row_ids` field alongside each merged/derived output row, even though nothing reads or displays it yet. This means historical pipeline runs aren't lost if/when real lineage tooling gets built later.

### Data transparency (Q8b)
Raw source tables (Open Data extract, FOI list, ownership_claims) are kept as **separate browsable SQLite tables**, not collapsed into one merged dataframe early in the pipeline. No lineage tracing between them yet (see above) — just visibility into inputs alongside the merged/final view.

### Sensitivity model (Q11)
**Field-level flags, tagged incrementally, default-public.** Not every field classified up front (too much upfront work for the time budget) — instead, known-sensitive fields are flagged now (tenant names/identifying details in claim notes; VTU membership is kept out of the pipeline entirely), everything else defaults to public, and new fields get flagged *at the moment they're added* if they touch tenant identity or membership. This is a discipline to maintain, not just a one-time setup.

**Public ownership data (2026-09-23).** LOTR reporting bodies and interest holders — including private individuals — are shown on the public map as the province publishes them; owners can seek removal through the registry's own channels. Claim provenance in public artifacts is limited to source *types* and counts: `public_registry` shows as "provincial registry", `city_record` (a City of Vancouver record, e.g. the SRO inventory naming the person behind a company) as "City records", every other type collapses to "VTU research" so the map never signals that a tenant reported on a landlord, and `source_note` never leaves the database (`metrics/portfolios.py::EVIDENCE_BUCKET`). A network's entity names are public even when only VTU research links them (ruling 2026-09-24) (a canary test in `tests/test_export_ownership.py` enforces this). Full provenance is for the internal app. Owners and operators named in the City's SRO inventory (an FOI release), including private individuals, are shown as published on the same basis (ruling 2026-09-24); the export expands the inventory's abbreviations (`sro_names.py::SRO_NAME_ALIASES`) and applies the curated corrections in `src/tc_core/sro_names.txt` (cut-off and misspelt names, joint owners, the person behind a company, a named lessee). Its `behind:` pairs become `city_record` claims via `uv run python scripts/update_sro_claims.py`. LOTR interest holders (including trustees, settlors and partners) are published with name, interest type and PIDs only; residence, citizenship and registered-address fields are never exported (`metrics/registry_owners.py::build_interest_holders` reads none of them; canary in `tests/test_export_ownership.py`).

### Export mechanism (Q12)
Two paths, sharing the same underlying "filter to public fields" logic in `tc_core`:
1. **Ad hoc export button** (in the internal app, not yet built) — download a filtered CSV/JSON of whatever's currently in view, for sharing with collaborators.
2. **Automated public feed** — the same filter logic feeds the public map's build step directly (`tc_core` → filter to public fields → JSON → public site build reads it). Keeps the public map in sync with real data without manual copy-paste.

The public contract is `tc_core/contract.py` (Pydantic models, `extra="forbid"`, no sentinel strings — missing is null): it is the allowlist of public fields for `building_records.json` and `networks.json`, and a record that doesn't validate fails the export. Buildings carry their parties in roles (owner on title, interest holder, manager, licensee) with source types and dates — see docs/superpowers/specs/2026-10-08-building-popup-and-contract-v2-design.md. `scripts/write_contract_schema.py` writes `frontend/src/contract.schema.json`; `npm run gen:types` generates the frontend's types from it.

---

## 4. Internal tool

**Status (2026-10-20): still a wish; requirements and vision are open, and so is the tech (Streamlit was the earlier pick, not a commitment).** Nothing is built. Rather than a generic browse/edit app, the plan is to pick **one concrete use case** and explore it in depth first. Candidates (none chosen):

- **Doorknocking tool** for VTU chapters
- **Research dashboard** — advanced queries and visualizations over the data in detail
- **Power-mapping tool** — understanding ownership patterns and landlord networks
- **Derived landlord index**

Whichever comes first, a single-record claim form (via `record_claim()`) is likely needed — today claims only enter through CSV/script imports.

Constraints that still hold regardless of use case:

| Decision | Answer |
|---|---|
| Access scope | **Single-user for now** (Q7) — read + write via forms, not raw SQL editing. Multi-user accounts deferred until there's an actual second organizer who needs it. |
| Data exploration | Raw source tables + merged/entity tables both browsable (Q8b) — see "Data transparency" above. |
| Hosting | **Local only**, but config (file paths, secrets) not hardcoded to this machine, so deploying later is a config change, not a redesign (Q10). Given the data includes tenant-reported and membership information, "reachable over the internet" is a real risk not worth taking on before there's a second user and a real auth plan. |

---

## 5. Public map

| Decision | Answer |
|---|---|
| Rebuild scope | **Yes, rebuild** — driven by performance and architecture, not visual polish (Q13 revised). Current Folium-based map bakes thousands of marker objects directly into a static HTML file at build time; this is the likely performance ceiling at city scale. |
| Map rendering | **Hand-written Leaflet** (same visual library as now, no Folium), with marker clustering/canvas rendering for scale. Not vector tiles (MapLibre GL) yet — current building counts don't need that, but the data export is shaped so upgrading later, if data volume grows enough to need it, is realistic (Q14). |
| Frontend tooling | **Vite + TypeScript, no framework** (Q15). Author's React experience (via Headstart, ~2016, pre-hooks) is real but rusty; relearning React well enough to use confidently is a bigger time cost right now than managing map/filter/table state sync by hand in TypeScript. Can migrate *to* a framework later once the JSON data contract is stable — the hard part (data) won't need to change. |
| Data flow | Python pipeline's job becomes: produce clean JSON/GeoJSON only. All rendering, filtering, and interactivity logic moves to the TypeScript frontend. |

---

## 6. Engineering practices

| Decision | Answer |
|---|---|
| Deployment/CI | **Manual deploy, no CI** (Q17, revised 2026-10-20). `uv run deploy` builds the frontend and publishes it to the `production` build-output branch (GitHub Pages, map.tenantcommons.ca). CI and scheduled rebuilds are deferred. |
| Testing | **Targeted, not broad** (Q18). Automated tests specifically on: (1) the public/sensitive field-filtering logic, and (2) claims-merge logic — because silent regressions there are actively dangerous (data leak risk / corrupting the core IP asset). Everything else (address matching, block aggregation, rendering) gets sanity-checked by eyeballing output on the current (still-small) dataset, not formal tests. |

---

## 7. Where it stands & what's next to share

**Current state (2026-10-20):** the public map is live at map.tenantcommons.ca and circulating among a small group — VTU organizers and tenant organizers across Canada and North America. It does a decent job of showing the potential, but on its own it isn't clearly different from tools like WhoOwnsWhat or the Anti-Eviction Mapping Project.

**Next shareable version:** one that demonstrates the other uses of the data — **collaboration, claims, curation and community knowledge**. "Here's a building, here's who really owns it, here's how we know, and here's how organizers add to it." Shape not yet decided; likely tied to the internal-tool use case chosen in Section 4.

**Depth over breadth still holds for research:** a small set of well-known cases (existing VTU organizing, already-pieced-together shell-company ownership) made airtight — accurate data, real ownership_claims, clear provenance — shows the claims layer better than coverage numbers. While researching a known case, capture threads into other buildings as `ownership_claims` even if those buildings aren't researched yet; this seeds breadth cheaply.

**Risk to guard against:** convenience shortcuts (especially around sensitivity filtering) quietly becoming permanent. Re-check the public-export gate before every deploy.

---

## 8. Build sequencing

The thin vertical slice (SQLite → export → Vite/Leaflet map) is done and live. Work now deepens layer by layer: the ownership model (Section 3), the public map, and an internal-tool use case (Section 4).

---

## 9. Task breakdown

### Phase 0 — Thin slice (done)

SQLite schema, ingest for Open Data / FOI (plus LOTR, SRO, co-ops, rezoning, listings), merge/dedup with `source_row_ids`, the public-field allowlist (`contract.py`), and the Vite + TypeScript Leaflet map with sidebar tables — all built and live. The Streamlit app from the original Phase 0 was never built; it's superseded by Section 4.

### Phase 1 — Deepen

**`tc_core`**
- [x] Build `ownership_claims` table per schema in Section 3 (incl. `claim_key`)
- [x] Bulk-CSV import for `ownership_claims` (`ingest/ownership_claims.py`), upserting by `claim_key` so a research spreadsheet can be re-imported safely — see "Claims ingestion" above
- [x] Shared `record_claim()` write path + entity-resolution convention (`same_entity`/`common_owner`) — see "Claims ingestion" above
- [x] Per-source `ingest_runs` tracking (success/failure history for every ingest run, not just claims) — see "Ingest run tracking" above
- [x] Targeted tests: sensitivity-filter logic, claims-merge logic (`tests/test_export_*.py`, `tests/test_claims_*.py`)
- [x] Public export excludes sensitive fields, test-covered (canaries in `tests/test_export_ownership.py`, `tests/test_export_artifacts.py`)
- [ ] Populate claims for the small, deep case set you already know well
- [ ] Opportunistically capture city-wide ownership claims surfaced during that research (unpolished, seed data only)
- [x] Classify entities and buildings (owner type, legal form, market status, operator, scale), with attribute claims for corrections and institutional owners — see "Building classification" in Section 3
- [ ] Explore what a BODS-like ownership model looks like against the current claims + parties-in-roles data — see "Ownership modeling direction" in Section 3

**Internal tool**
- [ ] Pick one use case from Section 4 and work out its requirements and vision
- [ ] Single-record add/edit form and retract (not delete) UI for `ownership_claims`, via `record_claim()`
- [ ] Ad hoc export button (filtered CSV/JSON for sharing)

**Public map**
- [x] Wire in claims-derived landlord clustering (grouping shell companies under a real owner where confirmed)
- [x] Separate each building's owner (LOTR reporting body or licence holder) from its landlord network, with provenance indicators — see docs/superpowers/specs/2026-09-23-ownership-layers-design.md
- [x] Popup v2: tabbed Summary / Ownership chain / Building on export contract v2 — see docs/superpowers/specs/2026-10-08-building-popup-and-contract-v2-design.md
- [x] Owner type / legal form / rents filters and landlord-portfolio sliders (spec 2026-10-20)
- [ ] Polish filters/sidebar to match or exceed current site's functionality (neighbourhood, assessed value, unit sliders)
- [ ] Marker clustering/canvas rendering if point count warrants it

**Next shareable version:** shows collaboration, claims, curation and community — see Section 7.

### Phase 2 — Not yet scoped (deliberately deferred)
- Deployment/CI automation (GitHub Actions → Pages, or scheduled rebuilds)
- Multi-user accounts for the internal app
- Vector tiles (MapLibre GL) — only if/when data volume makes Leaflet performance a real problem
- Broader `claims` model generalization (building condition, renoviction, campaign stage, etc.)
- Converging the data model with the separate RTB-decisions project
- Other municipalities/collaborators — only with funding

---

## Open questions / not yet decided
*(add here as they come up)*

- **Buildings spanning several parcels/folios (raised 2026-10-06).** `prepare/buildings.py::collapse_parcels()` is a stopgap: it sums assessed values and tax across a building's folios and takes every other column from the highest-value folio. That fixed values being picked at random per run, but it still flattens the building to one parcel's attributes. *Ownership half resolved 2026-10-08:* each owner and interest-holder party now carries its own PIDs, so the popup says "jointly owned by A and B" for one parcel and lists owners per parcel otherwise (air space parcels like 179 Main St). Values and other attributes are still flattened — revisit `collapse_parcels()` for those. Ownership-sector classification is now built per owner party (docs/superpowers/specs/2026-10-20-building-classification-design.md); a building's values are still one parcel's.