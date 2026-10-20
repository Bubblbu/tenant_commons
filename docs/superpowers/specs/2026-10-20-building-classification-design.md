# Building classification — design

*2026-10-20. Resumes the sector classification paused on 2026-10-06 (CLAUDE.md, Open questions).*

> **Implemented 2026-10-20** (branch `feature/building-classification`). Planning and implementation refined several points; they are listed under "Refinements" at the end and win over the body where the two differ.

## Goal

Classify every building and every owner entity along a few independent axes, so that:

- **tenants** see what kind of landlord they have (popup),
- **organizers** can filter by owner type, legal form, market status and portfolio size (power-mapping),
- **research** can total units and buildings by type with plain SQL over derived tables,
- **the claims layer** is tested in a new way: claims *about one entity* (its kind, whether it is institutional), entered by organizers like any other claim.

The four uses carry equal weight. The axes stay separate; there is no single combined label. "Mixed" is computed from them, never assigned by hand.

## Decisions

| Question | Decision |
|---|---|
| Axes | Owner type, private legal form, scale, market status, operator type — kept separate |
| Private split | Legal form (individual / company / numbered company / trust / partnership); scale from network size; institutional flag (REIT, pension fund, …) from claims only |
| Where classification lives | On **entities** (`Party.kind`, `NetworkEntity.kind`); a building's owner type is derived from its owner parties |
| Market status | Evidence where a source says non-market; otherwise `market (inferred)` for privately owned buildings; else unknown |
| Buildings with no owner on title | Infer from City-owned land, co-op, SRO and non-market evidence; then from the **licence holder's legal form** as a weaker, labelled signal (option B′ below) |
| City land under a private leasehold | `owner_type: mixed`, reason "public land, private leasehold" |
| Attribute claims | Stored in `ownership_claims` with the value in `entity_b`, as `network_label` already does — no new table |
| Surfaces (this spec) | Popup headline + basis; sidebar filters; two portfolio-size sliders |

### Why the licence holder is a weak signal, not the owner (B′)

By-law 4450 requires a licence of whoever "carries on" a business (s. 3(1)); Long Term Rental is "a business providing residential rental accommodation" for a month or more. The owner's duty is only not to permit an unlicensed business on their premises (s. 3(16)). So the licensee is whoever runs the rental business — usually the owner, but not necessarily.

In the 2026-10-20 export, of 463 buildings with both a licensee and a registry owner, 315 match exactly, 2 are the manager, and 146 differ. Some of the 146 are spelling variants (Moberley / MOBERLY Investments, YWCA / Young Women's Christian Association), the rest are affiliated companies (262109 B C Ltd vs Zen Family Holdings), non-profit operators on private title (Urban Vision Housing Society) and leasehold structures (Concert Properties vs VLC Leaseholds). That is roughly 75–80% agreement: enough to feed an owner *type* with a lower-confidence basis, not enough to call the licensee the owner. The licensee never becomes an owner party; it only fills the owner-type axis where nothing better exists, and the registry always wins.

## Vocabulary

### Entity level

| field | values |
|---|---|
| `kind` | `government`, `non_profit`, `coop`, `individual`, `company`, `numbered_company`, `trust`, `partnership`, `unknown` |
| `institutional` | `null`, or `reit`, `pension_fund`, `insurer`, `asset_manager`, `other` — **claims only**, never inferred |

- `kind` comes from ordered name rules (numbered prefix with or without dots; Ltd/Inc/Corp; Society/Foundation/Association/church; "Co-op Housing Association"; a list of known government bodies; "Surname, Given" person format) and from LOTR interest type (`settlor` → `trust`). Order matters: government bodies are matched by name, not by "British Columbia" appearing in the string.
- A confirmed, active `entity_kind` claim overrides the rules — the correction path.
- The SRO inventory's `chinese_society` sector maps to `non_profit` here; `Sro.owner_sector` keeps its finer label.

### Building level — `classification`

Every axis is an `Axis`: `value`, `basis` (list of `Basis`), `inferred` (bool).

1. **`owner_type`**: `government` / `non_profit` / `coop` / `private` / `mixed` / `unknown`, plus `legal_forms` (list of private `kind`s) and `parts` (owner types, when `mixed`) and `reason` (e.g. `public_land_private_leasehold`, `owners_differ`). Precedence, first that applies:
   1. confirmed `entity_kind` claims on the owner parties
   2. registry owners' kinds (name rules)
   3. City-owned properties dataset → `government`
   4. co-op (`non_profit` co-op → `coop`), SRO owner sector, non-market list operator → inferred
   5. licence holder's kind → inferred, basis `licence`
   6. `unknown`

   `mixed` when owner parties (across parcels, or joint owners) have different owner types, or when the City-owned dataset holds the land and the registry owner is private (`public_land_private_leasehold`).
2. **`market`**: `non_market` / `market` / `unknown`.
   - Evidence: City non-market housing list, non-profit co-op, government owner.
   - Inferred `non_market`: SRO with a non-profit or government owner or operator.
   - Inferred `market`: owner type `private` with no non-market evidence; equity co-op.
3. **`scale`**: `single` / `small_portfolio` / `large_portfolio`, from the building's network size in buildings on the map; null with no owner or licensee. Shown in the popup headline only — the filter is the portfolio sliders below.
4. **`operator_type`**: same vocabulary as `owner_type`, from the non-market list operator, SRO operator, manager party or licensee. Popup only; no filter yet.

### Basis

A closed `Literal`: `name_rule`, `registry`, `licence`, `city_owned`, `non_market_list`, `chf_bc`, `sro_inventory`, `network`, and claim buckets `claim_registry`, `claim_city_records`, `vtu_research`. Claim source types collapse through `metrics/portfolios.py::EVIDENCE_BUCKET` exactly as network evidence does: `public_registry` → `claim_registry`, `city_record` → `claim_city_records`, everything else → `vtu_research`.

### Portfolio metrics

Per building, computed at export:

- **`portfolio_units`** — total units of the buildings on the map in its network.
- **`portfolio_value`** — total assessed value (land + building) of the same buildings.

A building whose owner or licensee has no network is its own portfolio; with neither, both are null. These are lower bounds: only rental buildings on this map count (no rented condos, commercial holdings or property outside Vancouver), and the UI says so. `NetworkTotals` gains `assessed_value`.

## Architecture

### New raw source: City-owned properties

`ingest/raw_city_owned.py` loads `raw/cov_open_data/city-owned-properties.csv` (semicolon-separated) verbatim into `raw_city_owned_properties`, with stable row IDs, logged to `ingest_runs`. Joins to buildings on `land_coord` = the folio's first 8 digits. The `type` column (CAPITAL FUND, PEF, …) is kept for later. Entry in `docs/DATA_SOURCES.md` and the source's `MANIFEST.md`.

### Claims

Two constants in `claims.py`, beside `NETWORK_LABEL`:

- `ENTITY_KIND` — `entity_b` is a `kind` value
- `INSTITUTIONAL` — `entity_b` is an `institutional` value

`record_claim()` validates `entity_b` against the vocabulary for these relationships and stores it verbatim (not through `clean_owner_label()`). Their values are excluded from `list_known_entities()` / `find_similar_entity()`, as label values are. A resolver `entity_attribute_claims(conn, relationship, include_unconfirmed=False)` returns, per normalized entity key, the most recently updated active claim's value and source type; confirmed-only by default. Both claim types enter through the existing CSV and `scripts/update_claims.py`.

### `metrics/sector.py`

Pure functions, no I/O:

- `classify_entity(name, interest, claim) -> EntityKind` (kind, institutional, basis, inferred)
- `classify_building(owners, interest_holders, licensee, city_owned, coop, sro, non_market, network_size, thresholds) -> Classification`
- `scale_for(network_size, thresholds)`

Name rules are an ordered table in the module.

### Research outputs

`scripts/classification_report.py` reads the exported `building_records.json` and writes `data/derived/classification/buildings.csv` (one row per building: owner type, legal forms, parts, reason, basis, inferred; market; operator; scale; network) and `entities.csv` (name, role, kind, institutional, buildings), plus a printed report for eyeballing. Not public. (Not SQLite tables: `rebuild_data.py --skip-ingest` must never write to the database.)

### Export and contract (v5)

- `contract.py`: `Kind`, `Institutional`, `Basis` literals; `Axis`, `OwnerAxis`, `Classification` models; `Party.kind: Kind | None` and `Party.institutional: Institutional | None`; `NetworkEntity.kind: Kind` (replaces `person | company`); `NetworkTotals.assessed_value: Int | None`; `Building.classification: Classification`; `schema_version` 5.
- `export_parties.py` fills `Party.kind` / `institutional` from `entity_kinds`.
- `export.py` attaches `classification`, `portfolio_units`, `portfolio_value`.
- `filter_config.json`: facet values with counts for owner type, legal form and market; `portfolio_units` and `portfolio_value` as metrics (histogram bins, log scale) under a "Landlord portfolio" heading.
- `scripts/write_contract_schema.py` → `npm run gen:types`.

### Config

```toml
[classification]
small_portfolio_min = 2
large_portfolio_min = 10
```

## Public exposure

Classifications describe entities and buildings, not tenants, so they are public by default (CLAUDE.md §3, Sensitivity model). Guards:

- Claim-derived basis is bucketed; `source_note` and `reported_by` never leave the database.
- `Basis` is a closed literal; an unknown basis fails the export.
- An `institutional` or `entity_kind` claim from a tenant report shows only as "VTU research", like `common_owner` claims.

## Frontend

**Popup, Summary tab:** one headline, e.g. *Private · numbered company · large portfolio · market (inferred)*. Inferred parts are styled softer, with an ⓘ giving the basis in words ("from rental licence holder; not confirmed on title"; "private owner, not on the City's non-market list"). `mixed` names its parts ("City land, private leasehold").

**Popup, Ownership chain tab:** a kind chip on each owner and interest-holder party, "Institutional: pension fund" when claimed, and the operator type beside the operator or manager. Network members are grouped by the new `kind` ("2 people, 1 company, 2 numbered companies, 1 society") in `popup/ownership.ts`.

**Sidebar filters:**

- Owner type — multi-select; `mixed` buildings match any of their parts
- Legal form — enabled when Private is selected
- Market status
- **Include inferred** — on by default; off counts only evidence-backed values
- **Landlord portfolio** — `portfolio_units` and `portfolio_value` sliders via the existing `metric-controls.ts`; ⓘ text: "assessed value of their rental buildings on this map — a lower bound". Null values pass, as for the existing sliders.

Reset filters clears all of them.

## Testing

Targeted, per CLAUDE.md §6.

- `tests/test_classification_claims.py`: vocabulary validation for `entity_kind` / `institutional`; latest confirmed claim wins; retracted claims stop applying; unconfirmed ignored by default; attribute values never appear in `list_known_entities()` / `find_similar_entity()`.
- `tests/test_classification_rules.py`: fixture names — Sun Life Assurance Company of Canada, Mennonite Senior Citizens Society of British Columbia, "Moore, Kathleen Frances", `0888189 B.C. Ltd.` / `372328 BC Ltd`, YWCA British Columbia, CLT 0005 Community Society, BC Housing, City of Vancouver, a settlor; the precedence ladder; leasehold → `mixed`; licence-only → inferred with basis `licence`.
- `tests/test_export_ownership.py` additions: canary that a tenant-report `entity_kind` claim's `source_note` and reporter appear in neither artifact; claim basis is bucketed; an unknown basis fails validation.
- Frontend: fixtures updated; a filter test for the inferred toggle, legal form gating, `mixed` matching, and the portfolio sliders.

**Eyeball check:** `scripts/classification_report.py` prints counts per axis, the 50 most common `name_rule` classifications, every `mixed` building, and owner/licensee kind disagreements. Run before merge.

## Research queries (examples)

```bash
uv run python scripts/classification_report.py
sqlite3 :memory: \
  ".import --csv data/derived/classification/buildings.csv b" \
  "SELECT owner_type, market, COUNT(*), SUM(units) FROM b GROUP BY 1, 2 ORDER BY 4 DESC;" \
  "SELECT local_area, ROUND(1.0 * SUM(CASE WHEN owner_legal_forms LIKE '%numbered_company%' THEN units END) / SUM(units), 3)
     FROM b WHERE owner_type = 'private' GROUP BY 1 ORDER BY 2 DESC;"
```

## Rollout

Rebuild (`prepare_data.py`, then `rebuild_data.py`), compare snapshots with `scripts/compare_snapshots.py` (only the new fields and tables should change), run the classification report, re-check the public-export gate, then `uv run deploy` with the author's OK.

## Out of scope

Colour-by mode and legend; a totals panel; operator-type filter; a form for entering classification claims (internal tool, CLAUDE.md §4); splitting City-owned land by fund type; per-folio values (`collapse_parcels()`).

## Refinements (planning and implementation, 2026-10-20)

1. **Nothing known is null, never `"unknown"`.** The contract already bans sentinel strings (`test_v2_has_no_sentinels`). `Kind` and `OwnerType` have no `unknown`; `classification.owner` and `classification.market` are null when nothing is known; `NetworkEntity.kind` is nullable; `entity_kind` claims cannot say `unknown`. `metrics/sector.py` keeps `"unknown"` internally.
2. **The leasehold reason is `public_land_leasehold`** and covers any non-government owner on City land. 9 of the first 11 cases are non-profit or co-op leaseholders; the popup names the leaseholder type ("City land, non-profit leasehold").
3. **Registry holder type is evidence for `individual`**; a registry corporation is never an individual. "Settlor → trust" is dropped (a settlor created the trust; it is not the trust). `trust` comes from the name or a claim.
4. **`inferred` on the owner axis** means the owner type came from something other than a registry owner, a claim or the City-owned list. Name rules applied to a registry owner don't make it inferred; the basis still lists `name_rule`.
5. **Name rules** gained: association/benevolence → non-profit; Metro Vancouver Housing → government; "NNNNNN British Columbia Ltd" → numbered company; plain two-to-four-word names without organisation words ("Chris Wall") → individual, as the old network kind guess had it.
6. **Portfolio sliders read network totals** (`NetworkTotals.units`, new `assessed_value`). Buildings carry no portfolio fields. The 2,330 buildings with no landlord on record share the sentinel network key `"unknown"` and are excluded from portfolios and scale.
7. **No facet counts** in `filter_config.json`; the chips are static HTML like the housing chips.
8. **`Basis`** gained `listing` (operators from manager listings) and lost `network`.
9. **Coverage.** The licence-holder fallback (B′) only helps buildings that have a licence holder. The 2,330 buildings with neither owner nor licensee stay unclassified unless City land, co-op, SRO or non-market evidence applies. First build: owner type known for 2,489 of 5,588 buildings (private 1,949, government 259, non-profit 187, co-op 83, mixed 11); market status known for 2,542.
10. **Sidebar layout (after review with the author).** Every Filter by section is collapsible, with its count and Clear on the heading: Area (open), Landlord (open: picker, "Landlord on record", the two portfolio sliders), Owner type (collapsed: type, legal form, rents, "Include inferred"), Building (collapsed), Assessed value (collapsed). There is no separate Landlord portfolio section.
