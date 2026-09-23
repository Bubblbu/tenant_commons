-- ============================================================
-- REBUILDABLE — safe to DROP + recreate on every ingest run.
-- Derived from source CSVs; nothing here is hand-authored.
-- ============================================================

DROP TABLE IF EXISTS vtu_membership;
DROP TABLE IF EXISTS buildings;
DROP TABLE IF EXISTS landlords;
DROP TABLE IF EXISTS blocks;
DROP TABLE IF EXISTS raw_addresses;
DROP TABLE IF EXISTS raw_buildings;
DROP TABLE IF EXISTS raw_block_numbers;
DROP TABLE IF EXISTS raw_sro;
DROP TABLE IF EXISTS raw_coops;
DROP TABLE IF EXISTS raw_rezoning;
DROP TABLE IF EXISTS overlay_housing;
DROP VIEW IF EXISTS block_stats;

CREATE TABLE raw_buildings (
    raw_building_id INTEGER PRIMARY KEY,
    local_area TEXT,
    address TEXT,
    secondary_addresses TEXT,  -- semicolon-joined list of other civic addresses VanMaps resolves to this same building
    primary_address TEXT,
    is_primary_address INTEGER,
    n_pids INTEGER,
    pid TEXT,                  -- semicolon-joined list when a building spans multiple PIDs
    folio TEXT,                -- semicolon-joined list, same reason
    units INTEGER,
    year_built INTEGER,
    bsns_group TEXT,
    bsns_name TEXT,
    bsns_trade_name TEXT,
    bsns_type TEXT,
    bsns_subtype TEXT,
    value_land TEXT,        -- verbatim: source mixes plain numbers and "$..." strings; parse at merge time
    value_bldg TEXT,        -- verbatim, same reason
    bldg_land_ratio REAL,
    value_per_unit TEXT,
    zoning TEXT,
    zoning_district TEXT,
    zoning_classification TEXT,
    name TEXT,
    management TEXT,
    n_issues INTEGER,
    issues_details TEXT,
    notes TEXT,
    prospect TEXT,
    ingested_at TEXT NOT NULL
);
CREATE INDEX idx_raw_buildings_address ON raw_buildings(address);
CREATE INDEX idx_raw_buildings_local_area ON raw_buildings(local_area);

CREATE TABLE raw_addresses (
    raw_address_id INTEGER PRIMARY KEY,
    civic_number TEXT,
    geo_local_area TEXT,
    geom TEXT,
    p_parcel_id TEXT,
    pcoord TEXT,
    site_id TEXT,
    std_street TEXT,
    note TEXT,
    geo_point_2d TEXT,      -- "lat, lon" verbatim
    ingested_at TEXT NOT NULL
);
CREATE INDEX idx_raw_addresses_street ON raw_addresses(std_street);
CREATE INDEX idx_raw_addresses_civic ON raw_addresses(civic_number);

-- Vancouver Open Data's "block-numbers" dataset: one point per city block,
-- carrying the City's own authoritative geo_local_area — used only to
-- resolve local_area for blocks with zero buildings (see export.py /
-- spatial.py's resolve_local_area_from_block_numbers).
CREATE TABLE raw_block_numbers (
    raw_block_number_id INTEGER PRIMARY KEY,
    label TEXT,
    geo_local_area TEXT,
    geom TEXT,
    geo_point_2d TEXT,      -- "lat, lon" verbatim
    ingested_at TEXT NOT NULL
);

-- SRO/SRA, co-op, and rezoning-application sources: raw storage only, for
-- browsability (CLAUDE.md Q8b). Address/name-key matching against buildings
-- runs at ingest time, in src/tc_core/ingest/overlays.py (see
-- ingest/overlay_write.py), writing flags onto `buildings` and unmatched
-- records to `overlay_housing`. See docs/DATA_SOURCES.md for each source's
-- (partially unverified) origin.
CREATE TABLE raw_sro (
    raw_sro_id INTEGER PRIMARY KEY,
    source_id TEXT,            -- the source's own "ID" column
    address TEXT,
    building_name TEXT,
    secondary_address TEXT,
    area TEXT,
    latitude REAL,
    longitude REAL,
    owner TEXT,
    operator TEXT,
    operator_group TEXT,
    ownership_group TEXT,
    registered_rooms INTEGER,
    occupancy_status TEXT,
    match_method TEXT,        -- upstream address-matching flag from whoever combined the source lists; unrelated to our own matching
    ingested_at TEXT NOT NULL
);
CREATE INDEX idx_raw_sro_address ON raw_sro(address);

CREATE TABLE raw_coops (
    raw_coop_id INTEGER PRIMARY KEY,
    source_id TEXT,            -- the source's own "id" column
    title TEXT,
    city TEXT,
    region TEXT,
    neighbourhood TEXT,
    school_district TEXT,
    address TEXT,
    lat REAL,
    lon REAL,
    status TEXT,
    ownership_model TEXT,
    bedrooms_min REAL,
    bedrooms_max REAL,
    home_types TEXT,
    features TEXT,
    summary TEXT,
    featured_image TEXT,
    website TEXT,
    read_more_url TEXT,
    ingested_at TEXT NOT NULL
);
CREATE INDEX idx_raw_coops_address ON raw_coops(address);

CREATE TABLE raw_rezoning (
    raw_rezoning_id INTEGER PRIMARY KEY,
    source_id TEXT,            -- the source's own "ID" column (e.g. "RZ285"); NOT reliably unique per row
    name TEXT,
    status TEXT,
    category TEXT,
    status_detail TEXT,
    latitude REAL,
    longitude REAL,
    link TEXT,
    ingested_at TEXT NOT NULL
);

-- SRO/co-op source records whose address matched no building (see
-- ingest/overlays.py). Deliberately NOT merged into `buildings`: these are a
-- matching *failure* artifact, not buildings we have property data for.
-- Keeping them separate means COUNT(*) over `buildings` stays correct without
-- remembering to filter, and this table's own row count is a visible
-- data-quality metric — if it grows, address matching regressed.
-- The export unions the two (see export.py) with a real `source` discriminator.
CREATE TABLE overlay_housing (
    overlay_id INTEGER PRIMARY KEY,
    addr_key TEXT NOT NULL,
    address TEXT,
    housing_name TEXT,
    local_area TEXT,
    lat REAL,
    lon REAL,
    is_coop INTEGER NOT NULL DEFAULT 0,
    is_sro INTEGER NOT NULL DEFAULT 0,
    coop_status TEXT,
    coop_ownership_model TEXT,
    coop_url TEXT,
    sro_owner TEXT,
    sro_operator TEXT,
    sro_operator_group TEXT,
    sro_ownership_group TEXT,
    sro_occupancy_status TEXT,
    sro_registered_rooms TEXT,
    units INTEGER,  -- fallback for unmatched SRO records: registered_rooms, a room still houses a tenant
    source_row_ids TEXT,   -- lineage hook (CLAUDE.md Q8c): JSON {"raw_coops": [ids], "raw_sro": [ids]}
    ingested_at TEXT NOT NULL
);
CREATE INDEX idx_overlay_housing_addr_key ON overlay_housing(addr_key);

CREATE TABLE blocks (
    block_id INTEGER PRIMARY KEY,
    geom TEXT NOT NULL,               -- GeoJSON polygon, verbatim
    in_west_end_bbox INTEGER NOT NULL DEFAULT 0,
    source_row_ids TEXT,
    ingested_at TEXT NOT NULL
);

CREATE TABLE landlords (
    landlord_id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,       -- via clean_owner_label()
    owner_key TEXT NOT NULL,          -- via sanitize_owner()
    source_row_ids TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_landlords_owner_key ON landlords(owner_key);

CREATE TABLE buildings (
    building_id INTEGER PRIMARY KEY,
    addr_key TEXT NOT NULL UNIQUE,
    address TEXT NOT NULL,
    local_area TEXT,
    lat REAL,
    lon REAL,
    units INTEGER,
    year_built INTEGER,
    value_land NUMERIC,
    value_bldg NUMERIC,
    bldg_land_ratio REAL,
    n_issues INTEGER,
    landlord_id INTEGER REFERENCES landlords(landlord_id),
    block_id INTEGER REFERENCES blocks(block_id),
    source_row_ids TEXT,
    is_coop INTEGER NOT NULL DEFAULT 0,
    coop_status TEXT,
    coop_ownership_model TEXT,
    coop_url TEXT,
    housing_name TEXT,
    is_sro INTEGER NOT NULL DEFAULT 0,
    sro_owner TEXT,
    sro_operator TEXT,
    sro_operator_group TEXT,
    sro_ownership_group TEXT,
    sro_occupancy_status TEXT,
    sro_registered_rooms TEXT,
    is_rezoning INTEGER NOT NULL DEFAULT 0,
    rezoning_status TEXT,
    rezoning_status_group TEXT,
    rezoning_category TEXT,
    rezoning_status_detail TEXT,
    rezoning_link TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_buildings_landlord ON buildings(landlord_id);
CREATE INDEX idx_buildings_block ON buildings(block_id);
CREATE INDEX idx_buildings_local_area ON buildings(local_area);

-- Allow-listed columns only — see ingest/membership.py's ALLOWED_MEMBERSHIP_COLUMNS
-- (a later step). No name/email/phone/ethnicity/religion/donation data ever lands
-- here, even though the source NationBuilder export carries all of that.
-- Whole table is treated as non-public by default at export time (later step).
CREATE TABLE vtu_membership (
    membership_row_id INTEGER PRIMARY KEY,
    nationbuilder_id TEXT,
    addr_key TEXT,
    building_id INTEGER REFERENCES buildings(building_id),
    tag_list TEXT,
    updated_at TEXT,
    source_row_ids TEXT,
    ingested_at TEXT NOT NULL
);
CREATE INDEX idx_vtu_membership_addr_key ON vtu_membership(addr_key);
CREATE INDEX idx_vtu_membership_building ON vtu_membership(building_id);

-- Illustrative aggregate view — mirrors today's aggregate_blocks() shape.
-- Computed on read, never stored, so it can't go stale when a building changes.
CREATE VIEW block_stats AS
SELECT
    bl.block_id,
    COUNT(DISTINCT bd.building_id) AS buildings,
    COALESCE(SUM(bd.units), 0) AS total_units,
    COUNT(DISTINCT CASE WHEN vm.membership_row_id IS NOT NULL THEN bd.building_id END) AS member_buildings,
    COUNT(vm.membership_row_id) AS total_members
FROM blocks bl
LEFT JOIN buildings bd ON bd.block_id = bl.block_id
LEFT JOIN vtu_membership vm ON vm.building_id = bd.building_id
GROUP BY bl.block_id;

-- ============================================================
-- PERSISTENT — never dropped by rebuild. Hand-authored, irreplaceable.
-- Uses CREATE TABLE IF NOT EXISTS only. The ingest/rebuild routine must
-- never issue a DROP against anything in this section.
-- ============================================================

-- claim_key: a stable idempotency key, independent of claim_id (which doesn't
-- exist yet when a row is being drafted). Bulk-CSV imports (see
-- ingest/ownership_claims.py) require a human-authored one so re-running
-- against an edited research spreadsheet updates existing rows instead of
-- duplicating them; record_claim() auto-generates one (a UUID) for callers
-- that don't supply one (e.g. a future single-record entry form). Always
-- present either way — never a sometimes-null column.
CREATE TABLE IF NOT EXISTS ownership_claims (
    claim_id INTEGER PRIMARY KEY,
    claim_key TEXT NOT NULL UNIQUE,
    entity_a TEXT NOT NULL,
    entity_b TEXT NOT NULL,
    relationship TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_note TEXT,
    reported_by TEXT,
    date_reported TEXT,
    confidence TEXT NOT NULL DEFAULT 'unconfirmed' CHECK (confidence IN ('unconfirmed','confirmed')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retracted')),
    retracted_at TEXT,
    retracted_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_entity_a ON ownership_claims(entity_a);
CREATE INDEX IF NOT EXISTS idx_claims_entity_b ON ownership_claims(entity_b);
CREATE INDEX IF NOT EXISTS idx_claims_status ON ownership_claims(status);

-- Pipeline run history — tracks every source ingested on every run_ingest()
-- invocation, not just claims. Flat: one row per (run_id, source_name).
-- Never dropped, same persistence invariant as ownership_claims, for the
-- same reason — losing run history on every rebuild would defeat the point
-- of keeping it. See ingest/tracking.py.
CREATE TABLE IF NOT EXISTS ingest_runs (
    run_entry_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success','failure')),
    row_count INTEGER,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_run_id ON ingest_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_source ON ingest_runs(source_name);

-- Verbatim dump of a Samwise (BC Land Owner Transparency Registry research
-- tool) export: one row per (property, reporting corporation, disclosed
-- interest holder) declaration. PERSISTENT rather than REBUILDABLE like the
-- other raw_<source> tables — unlike raw_sro/raw_coops/raw_rezoning, this
-- source isn't wired into run_ingest() (it's imported standalone via
-- scripts/import_lotr_claims.py whenever Samwise produces a fresh export),
-- so it must survive a normal pipeline rebuild's init_db() call rather than
-- being dropped alongside buildings/addresses. ingest/raw_lotr.py does its
-- own delete-and-reinsert on each run instead, for the same idempotent-
-- reimport behaviour the REBUILDABLE tables get from init_db().
CREATE TABLE IF NOT EXISTS raw_lotr_ownership (
    raw_lotr_ownership_id INTEGER PRIMARY KEY,
    pid TEXT,
    reporting_body_name TEXT,
    reporting_body_kind TEXT,
    reporting_body_capacity TEXT,
    reporting_body_category TEXT,
    reporting_body_party_type TEXT,
    type_of_interest TEXT,
    holder_type TEXT,
    holder_name TEXT,
    obscure_message TEXT,
    individual_last_name TEXT,
    individual_given_names TEXT,
    individual_is_full_name_omitted TEXT,
    individual_is_canadian_citizen_or_pr TEXT,
    individual_principal_residence_city TEXT,
    individual_principal_residence_province TEXT,
    individual_principal_residence_country TEXT,
    individual_is_principal_residence_canada TEXT,
    individual_citizenship_country_codes TEXT,
    corporation_legal_name TEXT,
    corporation_registered_business_name TEXT,
    corporation_partnership_type TEXT,
    corporation_partnership_type_other TEXT,
    corporation_registered_address_line1 TEXT,
    corporation_registered_address_line2 TEXT,
    corporation_registered_address_city TEXT,
    corporation_registered_address_province_code TEXT,
    corporation_registered_address_province_name TEXT,
    corporation_registered_address_country_code TEXT,
    corporation_registered_address_country_name TEXT,
    corporation_registered_address_postal_code TEXT,
    corporation_is_head_office_different_from_registered TEXT,
    corporation_has_head_office TEXT,
    corporation_governing_laws_jurisdiction TEXT,
    corporation_incorporation_jurisdiction TEXT,
    corporation_continued_jurisdiction TEXT,
    order_id TEXT,
    order_created_date TEXT,
    search_by TEXT,
    search_text TEXT,
    is_exact_match TEXT,
    data_fetch_status TEXT,
    item_row_identifier TEXT,
    source_path TEXT,
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_lotr_ownership_pid ON raw_lotr_ownership(pid);
CREATE INDEX IF NOT EXISTS idx_raw_lotr_ownership_reporting_body ON raw_lotr_ownership(reporting_body_name);
