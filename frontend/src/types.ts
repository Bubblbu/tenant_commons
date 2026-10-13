/** Shapes of the artifact files (spec §4). Fields the frontend does not read are omitted. */
import type { FeatureCollection, Geometry } from 'geojson';
import type { Building, Network } from './contract.gen';

export interface MarkerRecord {
  b_id: number;
  lat: number | null;
  lon: number | null;
  owner_key: string | null;
  network_key: string | null;
  block_id: number | null;
  units: number | null;
  year_built: number | null;
  local_area: string | null;
  /** "co-op, sro" | "co-op" | "sro" | "" */
  housing_type: string;
  /** Outstanding rental-licence issues (City open data), null if unknown. */
  n_issues: number | null;
  /** "building" | "overlay_sro" | "overlay_coop" */
  source: string;
}

export interface NeighbourhoodSummary {
  name: string;
  count: number;
  units: number;
}

/** Chinatown / Villages Plan Areas — boundary overlays a building can belong
 * to in addition to (not instead of) its local_area. Rendered as two more
 * Filters > Neighbourhoods entries, after a separator. */
export interface SpecialAreaSummary {
  key: string;
  name: string;
  count: number;
  units: number;
}

export interface FilterConfig {
  schema_version: number;
  bounds?: { lat_min: number; lat_max: number; lon_min: number; lon_max: number } | null;
  neighbourhoods?: NeighbourhoodSummary[];
  special_areas?: SpecialAreaSummary[];
  blocks_total_units_max?: number | null;
  /** Business-licence data year of this build. */
  licence_year?: number | null;
  /** Median land share of assessed value across buildings (the popup's value-bar tick). */
  land_share_median?: number | null;
  [key: string]: unknown;
}

/**
 * The flat view of a building (flat.ts): what the tables, filters, landlord
 * picker, coverage panel and CSV export read. Missing values are null.
 */
export type BuildingRecord = { b_id: number } & Record<string, unknown>;

export interface BuildingData {
  schema_version: number;
  columns: string[];
  records: Record<string, BuildingRecord>;
}

export interface BlockProperties {
  block_id: number;
  block_label: string | null;
  local_area: string | null;
  buildings: number | null;
  total_units: number | null;
  median_year_built: number | null;
  in_chinatown?: boolean | null;
  in_village_plan?: boolean | null;
}

export type BlocksCollection = FeatureCollection<Geometry, BlockProperties> & { schema_version: number };

export interface BoundaryProperties {
  name?: string;
  /** The City's representative point for the area, when present. */
  geo_point_2d?: { lat: number; lon: number };
}

export type BoundaryCollection = FeatureCollection<Geometry, BoundaryProperties>;

/** villages_plan_areas.geojson: same shape as a boundary collection (name + polygon), no geo_point_2d. */
export type VillagesCollection = BoundaryCollection;

/** What the map draws: small enough to fetch before anything else. */
export interface MapArtifacts {
  filterConfig: FilterConfig;
  markers: MarkerRecord[];
  blocks: BlocksCollection;
  boundaries: BoundaryCollection;
  villages: VillagesCollection;
  chinatown: BoundaryCollection;
}

/** The building records and networks: the popup, tables and filters read these. */
export interface BuildingArtifacts {
  /** The flat view (flat.ts) of building_records.json. */
  buildingData: BuildingData;
  /** building_records.json as published: the popup reads these. */
  buildings: Record<string, Building>;
  networks: Record<string, Network>;
}
