/**
 * A tiny city for wiring tests: 10 buildings in 3 areas, two landlords in one
 * network, three buildings with no landlord on record (one with a manager),
 * and four blocks — one empty, and one (301, Strathcona) that also holds a
 * Downtown building, like the real block/building spatial-join quirk.
 */
import { markerStyle } from '../markers';
import type { BlocksCollection, BuildingData, BuildingRecord, FilterConfig, MarkerRecord } from '../types';

interface B {
  id: number; area: string; owner: string | null; units: number | null; year: number | null;
  housing: string; issues: number; block: number | null;
  chinatown?: boolean; village?: boolean; manager?: string; searched?: string;
}

const OWNERS: Record<string, { name: string; network: string; networkName: string }> = {
  acme: { name: 'Acme Holdings', network: 'nw1', networkName: 'Cedar Group' },
  birch: { name: 'Birch Properties Ltd', network: 'nw1', networkName: 'Cedar Group' },
};

const BUILDINGS: B[] = [
  { id: 1, area: 'West End', owner: 'acme', units: 40, year: 1965, housing: '', issues: 0, block: 101 },
  { id: 2, area: 'West End', owner: 'acme', units: 12, year: 1990, housing: 'sro', issues: 2, block: 101 },
  { id: 3, area: 'West End', owner: 'birch', units: 8, year: null, housing: '', issues: 0, block: 101, village: true },
  { id: 4, area: 'Downtown', owner: 'birch', units: 120, year: 2005, housing: 'co-op, sro', issues: 0, block: 201 },
  { id: 5, area: 'Downtown', owner: null, units: 30, year: 1930, housing: '', issues: 1, block: 201, chinatown: true, manager: 'Tribe Management' },
  { id: 6, area: 'Downtown', owner: null, units: null, year: 1912, housing: 'co-op', issues: 0, block: 201 },
  { id: 7, area: 'Strathcona', owner: 'acme', units: 6, year: 1908, housing: '', issues: 3, block: 301 },
  { id: 8, area: 'Strathcona', owner: null, units: 16, year: 1975, housing: '', issues: 0, block: 301, searched: '2026-10-06' },
  { id: 9, area: 'Strathcona', owner: 'birch', units: 60, year: 2015, housing: '', issues: 0, block: 301 },
  { id: 10, area: 'Downtown', owner: 'acme', units: 4, year: 1999, housing: '', issues: 0, block: 301 },
];

export const ALL_BIDS = BUILDINGS.map((b) => String(b.id));

function record(b: B): BuildingRecord {
  const o = b.owner ? OWNERS[b.owner] : undefined;
  return {
    b_id: b.id,
    address: `${100 + b.id} MAIN ST`,
    building_name: null,
    local_area: b.area,
    units: b.units,
    year_built: b.year,
    owner_key: b.owner,
    owner_name: o ? o.name : null,
    network_key: o ? o.network : null,
    network_name: o ? o.networkName : null,
    managed_by: b.manager ?? null,
    registry_no_filing: b.searched ?? null,
    housing_type: b.housing,
    n_issues: b.issues,
    block_id: b.block,
    in_chinatown: b.chinatown === true,
    in_village_plan: b.village === true,
    value_land: null,
    value_bldg: null,
    bldg_land_ratio: null,
  };
}

export const FIXTURE_BUILDING_DATA: BuildingData = {
  schema_version: 2,
  columns: ['b_id', 'address', 'local_area', 'units'],
  records: Object.fromEntries(BUILDINGS.map((b) => [String(b.id), record(b)])),
};

const FIXTURE_MARKER_RECORDS: MarkerRecord[] = BUILDINGS.map((b) => ({
  b_id: b.id,
  lat: 49.28 + b.id * 0.001,
  lon: -123.12,
  owner_key: b.owner,
  network_key: b.owner && OWNERS[b.owner] ? OWNERS[b.owner].network : null,
  block_id: b.block,
  units: b.units,
  year_built: b.year,
  local_area: b.area,
  housing_type: b.housing,
  n_issues: b.issues,
  source: 'building',
}));

export const FIXTURE_MARKERS = FIXTURE_MARKER_RECORDS.map((m) => ({ ...m, ...markerStyle(m) }));

function block(id: number, area: string, buildings: number, units: number) {
  const x = -123.12 + id * 0.0001;
  return {
    type: 'Feature' as const,
    geometry: { type: 'Polygon' as const, coordinates: [[[x, 49.28], [x + 0.001, 49.28], [x + 0.001, 49.281], [x, 49.28]]] },
    properties: {
      block_id: id, block_label: `Block ${id}`, local_area: area, buildings, total_units: units,
      median_year_built: null, in_chinatown: false, in_village_plan: false,
    },
  };
}

export const FIXTURE_BLOCKS: BlocksCollection = {
  type: 'FeatureCollection',
  schema_version: 2,
  features: [block(101, 'West End', 3, 60), block(201, 'Downtown', 3, 150), block(301, 'Strathcona', 4, 86), block(401, 'Strathcona', 0, 0)],
};

export const FIXTURE_FILTER_CONFIG: FilterConfig = {
  schema_version: 2,
  neighbourhoods: [
    { name: 'Downtown', count: 4, units: 154 },
    { name: 'Strathcona', count: 3, units: 82 },
    { name: 'West End', count: 3, units: 60 },
  ],
  special_areas: [
    { key: 'chinatown', name: 'Chinatown', count: 1, units: 30 },
    { key: 'village-plan', name: 'Villages Plan', count: 1, units: 8 },
  ],
  dataset_totals: { buildings: 10, units: 296 },
  blocks_total_units_max: 150,
  building_metric_order: ['units', 'year_built'],
  building_metrics: {
    units: {
      label: 'Units', min: 4, max: 120, step: 1, max_count: 6, format: 'number', type: 'int', decimals: 0,
      attr: 'units', use_log: false,
      bins: [{ start: 4, end: 40, count: 6 }, { start: 40, end: 80, count: 2 }, { start: 80, end: 120, count: 1 }],
    },
    year_built: {
      label: 'Year built', min: 1900, max: 2020, step: 1, max_count: 3, format: 'year', type: 'int', decimals: 0,
      attr: 'year-built', use_log: false,
      bins: [{ start: 1900, end: 1940, count: 3 }, { start: 1940, end: 1980, count: 3 }, { start: 1980, end: 2020, count: 3 }],
    },
  },
};
