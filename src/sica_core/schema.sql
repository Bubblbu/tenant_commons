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
