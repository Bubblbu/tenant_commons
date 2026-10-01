# Landlord listings as a building source

Date: 2026-09-30
Status: draft, awaiting review

## Problem

Landlords and property managers publish their own portfolios: Tribe (theliftsystem.com
feed), Dorset Realty Group (`scripts/fetch_dorset_listings.py`) and Wall Financial
Corporation (`scripts/fetch_wall_listings.py`). Snapshots accumulate in
`raw_manager_listings`, but today the only consumer is `building_names.py`, which
borrows listing names for buildings already on the map. Three things are lost:

1. **Buildings the City doesn't list.** Some listed rental buildings aren't in the
   rental inventory, the non-market list or the rental licences, even though the City
   has an address point for them. The 2026-09-30 snapshots have five: Whitehouse
   (1120 Pacific St, Wall), 1050 Burrard St, Newpointe Terrace (2223 W Broadway),
   ALMA Gastown (455 Abbott St) and the Center for Digital Media student apartments
   (685 Great Northern Way, Dorset).
2. **Who manages the building.** `managed_by` is only set when a known manager holds
   the rental licence. Most Dorset- or Tribe-managed buildings are licensed to the
   owning company, so the map doesn't show their manager and the manager filter
   can't find them.
3. **A link to the source.** The map never points to the company's own page for the
   building.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Which landlord sources | Portfolio listings only (the snapshot feeds above), not other web sources |
| Where a listing-only building is placed | Only at an exact match to a City address point. No geocoding, no feed coordinates |
| Unbuilt listings ("In Development", "Coming Soon") | Ignored entirely: they don't add buildings or links, and don't set a manager |
| Owner-operator feeds (Wall) | Never change the owner. Every listed building gets a uniform "Listed by <company> ↗" line |
| Who counts as a manager | Only companies in `data/curated/property_managers.toml`. Dorset Realty Group is added there alongside Tribe |
| Pickable in landlord search | Toml managers only. Owner-operators are found through their ownership group (claims) and owner names |
| Architecture | Approach A: listings are a fourth building source in the merge, ranked last |

## Design

### 1. Listing data

- **Status column.** `raw_manager_listings` gets a `status TEXT` column, written from the
  feed's `status` (Dorset: "3 units available", "Fully rented"; Wall: "Now Renting",
  "No Vacancy", "In Development"; Tribe: none). The table is PERSISTENT, so this is the
  project's first add-column migration.
  - `init_db` checks `PRAGMA table_info(raw_manager_listings)` and runs
    `ALTER TABLE raw_manager_listings ADD COLUMN status TEXT` when the column is missing.
  - The `CREATE TABLE` in `schema.sql` gains the column too, so new databases get it directly.
  - The upsert updates `status` with the same "newer snapshot wins" rule as name, address and URL.
- **Unbuilt statuses.** `UNBUILT_STATUSES = {"in development", "coming soon"}`, compared
  case-insensitively, defined in `ingest/manager_listings.py`.
- **Current listing.** A listing is current when its `last_seen` equals the latest
  snapshot date for its manager (`max(last_seen)` per `manager`). A listing that dropped
  out of the feed stays in the table as history but adds nothing to the map.
- **Usable listing.** Everything below uses only listings that are both current and not
  unbuilt.

### 2. Listings as a building source (merge)

- **Ingest order.** `run_ingest` moves `raw_manager_listings` (and `strata_lot_pids`)
  ahead of `run_merge`. Both are raw inputs and depend on nothing built by the merge.
- **Candidates.** A new function in `ingest/merge.py` (or a small
  `ingest/listing_buildings.py` it calls) turns usable listings into candidate building
  rows. A listing becomes a building only if both of these hold:
  1. It matches no building from the other three sources under `overlays._match_key`.
     This is the same exact, secondary and loose matching `building_names.py` uses, so
     "958 Bute St" vs. "936 Bute St" style near-misses don't create duplicates.
  2. Its `addr_key` exactly matches a City address point (`raw_addresses`). That address
     point supplies lat/lon and the local area.
- **Candidate fields.**
  - `building_source = "manager listing"`, appended last to `BUILDING_SOURCE_ORDER`, so
    any other source wins deduplication.
  - The owner is `(Unknown)`. Listings never supply an owner.
  - `units` comes from the feed when it has one (Wall's `numberOfRooms`, carried in the
    snapshot's `units` field and stored as a new nullable `units` column on
    `raw_manager_listings`); otherwise null.
  - No year built and no assessment.
- **Lineage.** The building's `source_row_ids` carries
  `raw_manager_listings:<listing_row_id>`, so it's clear which listing created it.
- **Rebuild log.** The rebuild prints each building added this way (manager, name,
  address), so a non-housing or mis-addressed listing is noticed on the first rebuild.
  There's no exclusions file. Add one only if a real case turns up.
- **Registry.** Strata buildings added this way carry the address point's plan number
  in their PID field, like other buildings. A `strata_lot_pids.csv` row for that plan
  lets an LOTR filing reach them (Whitehouse is VAS267).

### 3. Listings on buildings, export and popup

- **`building_listings`** (REBUILDABLE): one row per (building, usable listing), with
  columns `building_id, manager, url, last_seen, listing_row_id`.
  - Written in the same pass where `building_names.py` matches listings to buildings, so
    the export doesn't re-match.
  - Buildings created from a listing link to that listing.
- **Export columns.**
  - `listings`: a list of `{by, url, seen}` per building. `by` is the feed's company
    name; `url` and `seen` (`last_seen`) come from the listing. Public: it's the
    company's own marketing page. The listing row ID and external ID stay in the database.
  - `managed_by_source`: `licence`, `listing` or null.
- **`managed_by` rules** (`export.apply_property_managers`):
  1. **Licence rule, unchanged.** A toml manager holding the licence sets `managed_by`
     (`managed_by_source = "licence"`). Where the licence was the only owner source, the
     owner becomes not on record and the licence-based group falls back.
  2. **Listing rule, new.** Otherwise, a toml manager's usable listing sets `managed_by`
     to the manager name as the toml spells it (`managed_by_source = "listing"`). This
     never changes `owner_*` or `network_*`.
  3. A listing from a company not in the toml (Wall) never sets `managed_by`.
- **Popup** (`frontend/src/popup.ts`).
  - The manager line keeps the licence provenance for `licence`. For `listing` it shows
    "Company website, seen <date>".
  - Each listing adds "Listed by <by> ↗", linked through `safeUrl` with
    `target="_blank" rel="noopener"`. When `by` names the same company as `managed_by`
    (`sameName`), the link goes on the manager line instead of a second line.
  - Buildings with `building_source = "manager listing"`:
    - the size line says "<n> units" when the feed gave a count, and is left out
      otherwise;
    - a muted line "Added from <by>'s listings" says the City has no record of this
      rental building.
- **Filtering and search.** No new UI. The landlord picker's manager options, the table
  manager filter and the table text search already key off `managed_by` and the
  "Managed by …" cell text. Listing-derived `managed_by` makes every building a toml
  manager lists findable by that manager.
- **Feed names vs. toml names.** A feed may call its company something else than the
  toml does (Tribe's feed says "Tribe Rentals"). A toml entry can list
  `listing_names = ["Tribe Rentals"]`; the export maps those to the entry's `name`, both
  in `listings[].by` and for the listing rule.
- **Curated data.** Add `Dorset Realty Group` and `MetCap Living` as `[[manager]]` entries
  in `property_managers.toml`, with dated comments. MetCap Living
  (`scripts/fetch_metcap_listings.py`, 23 Vancouver buildings on 2026-09-30) manages for
  other owners and holds no Vancouver rental licence.
  - Where a Dorset company holds the licence and there's no registry filing, the owner
    becomes not on record. That's the intended licence-rule behaviour.
  - Dover Manor now has a registry owner, so it isn't affected.

### 4. Claim rows (research data, no code)

These are drafted into the claims CSV, reviewed, and imported with
`scripts/update_claims.py`. The user sets `confirmed` per row, and unconfirmed rows
don't cluster.

- **Dorset / Schuss.**
  - `common_owner` between Dorset Properties Limited and each registry entity whose
    filing names Ronald Joseph Schuss.
  - A `network_label` claim names the group "Dorset Realty / Schuss Family".
  - `source_type`: `public_registry` where the filing itself shows the link,
    `manual_research` otherwise.
  - `source_note` cites the filing PIDs and Dorset's portfolio page.
- **Wall Financial.**
  - `common_owner` between Wall Financial Corporation and W.F.C. Properties (Pacific)
    Inc., 0888189 B.C. Ltd., 1111 Seymour Residence Ltd, W.F.C. Properties (Brunswick)
    and 1136 Properties Ltd.
  - A `network_label` claim names the group "Wall Financial".
  - `manual_research`; `source_note` cites Wall's rental page and the listed building.
  - Wall & Redekop (a joint venture) is left out: `common_owner` could overstate it.

### 5. Sensitivity

- Every new public field (`listings[].by/url/seen`, `managed_by_source`, the
  "manager listing" building source) is the company's own published marketing.
- Snapshots may carry staff contact details. The ingest already stores only id, name,
  address, URL and dates; status and units are added to that list, and nothing else.
- The export canary in `tests/test_export_ownership.py` gets the new columns on its
  allow-list, plus a check that contact-like keys in a feed never reach a record.
- `source_note` stays internal as before.

## Testing

Targeted tests, per CLAUDE.md §6.

- **Python, listing ingest:**
  - `status`/`units` are stored, and the newer snapshot wins;
  - the migration adds `status` to an existing table without losing rows;
  - unbuilt and stale listings aren't usable.
- **Python, merge:**
  - an unmatched usable listing becomes a building only on an exact address-point match;
  - a loose-key match to an existing building adds nothing;
  - the other sources win deduplication;
  - the owner is `(Unknown)` and `source_row_ids` carries the listing tag.
- **Python, export:**
  - the listing rule sets `managed_by` and `managed_by_source = "listing"` only for toml
    managers, and never changes the owner or network;
  - the licence rule is unchanged;
  - `listings` is shaped `{by, url, seen}`.
- **Canary:** new columns are allowed, contact fields don't leak.
- **Frontend:**
  - the "Listed by" link, merged into the manager line when the companies match;
  - non-http(s) URLs aren't linked;
  - the "Added from … listings" line and units wording;
  - the picker counts a listing-managed building under its manager.

## Out of scope

- Other landlord web sources (news, permits, other directories).
- Geocoding listings that have no City address point (UBC/UEL buildings, North
  Vancouver addresses mislabelled "Vancouver").
- Showing unbuilt projects.
- A "Listed by" option in the landlord picker.
- The Samwise search-capture change (waits on an example LTSA search response).
