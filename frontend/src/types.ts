/** Shapes of the artifact files (spec §4). Fields the frontend does not read are omitted. */
import type { FeatureCollection, Geometry } from 'geojson';

export interface MarkerRecord {
  b_id: number;
  lat: number | null;
  lon: number | null;
  owner_key: string | null;
  block_id: number | null;
  units: number | null;
  year_built: number | null;
  local_area: string | null;
  is_vtu: boolean;
  member_count: number;
  /** "co-op, sro" | "co-op" | "sro" | "" */
  housing_type: string;
  /** "building" | "overlay_sro" | "overlay_coop" */
  source: string;
}

export interface NeighbourhoodSummary {
  name: string;
  count: number;
  units: number;
}

export interface FilterConfig {
  schema_version: number;
  bounds?: { lat_min: number; lat_max: number; lon_min: number; lon_max: number } | null;
  neighbourhoods?: NeighbourhoodSummary[];
  blocks_total_units_max?: number | null;
  blocks_member_building_max?: number | null;
  [key: string]: unknown;
}

/**
 * One row of building_records.json: the 41 columns of sica_core's
 * export.BUILDING_RECORD_COLUMNS, read defensively. Overlay text fields are ''
 * on building rows and null on overlay rows; treat both as empty.
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
  member_buildings: number | null;
  total_members: number | null;
  member_share: number | null;
}

export type BlocksCollection = FeatureCollection<Geometry, BlockProperties> & { schema_version: number };

export interface BoundaryProperties {
  name?: string;
  /** The City's representative point for the area, when present. */
  geo_point_2d?: { lat: number; lon: number };
}

export type BoundaryCollection = FeatureCollection<Geometry, BoundaryProperties>;

export interface Artifacts {
  filterConfig: FilterConfig;
  markers: MarkerRecord[];
  buildingData: BuildingData;
  blocks: BlocksCollection;
  boundaries: BoundaryCollection;
}
