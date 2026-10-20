/**
 * Loads the artifact directory once and checks its contract version (spec §4).
 * Two loads, so the map can draw before the much larger building records arrive.
 */
import { EXPECTED_SCHEMA_VERSION, artifactUrl } from './config';
import type { Building, BuildingRecordsFile, Network, NetworksFile } from './contract.gen';
import { FLAT_COLUMNS, flatten } from './flat';
import type {
  BlocksCollection,
  BuildingArtifacts,
  BoundaryCollection,
  BuildingData,
  FilterConfig,
  MapArtifacts,
  MarkerRecord,
  OverlayCollection,
} from './types';

export class ArtifactError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ArtifactError';
  }
}

/** Throws unless `payload.schema_version` is the version this frontend understands. */
export function checkSchemaVersion(name: string, payload: unknown): void {
  const version =
    payload && typeof payload === 'object' ? (payload as { schema_version?: unknown }).schema_version : undefined;
  if (version !== EXPECTED_SCHEMA_VERSION) {
    throw new ArtifactError(
      `${name}: expected schema_version ${EXPECTED_SCHEMA_VERSION}, got ${JSON.stringify(version)}. ` +
        'Rebuild the artifacts (uv run python scripts/rebuild_data.py) or update the frontend.',
    );
  }
}

async function fetchJson(name: string): Promise<unknown> {
  const url = artifactUrl(name);
  const resp = await fetch(url, { cache: 'no-cache' });
  if (!resp.ok) throw new ArtifactError(`${name}: HTTP ${resp.status} from ${url}`);
  return resp.json();
}

/** The nested buildings (for the popup) and their flat view (tables, filters, CSV). */
export function buildingViews(
  file: BuildingRecordsFile,
  networks: NetworksFile,
): { buildings: Record<string, Building>; networks: Record<string, Network>; buildingData: BuildingData } {
  const records = Object.fromEntries(
    Object.entries(file.records).map(([id, b]) => [id, flatten(b, networks.networks)]),
  );
  return {
    buildings: file.records,
    networks: networks.networks,
    buildingData: { schema_version: file.schema_version, columns: FLAT_COLUMNS, records },
  };
}

export async function loadMapArtifacts(): Promise<MapArtifacts> {
  const [filterConfig, markerMetadata, blocks, boundaries, overlays] = await Promise.all([
    fetchJson('filter_config.json'),
    fetchJson('marker_metadata.json'),
    fetchJson('blocks.geojson'),
    fetchJson('local-area-boundary.geojson'),
    fetchJson('overlay_areas.geojson'),
  ]);
  checkSchemaVersion('filter_config.json', filterConfig);
  checkSchemaVersion('marker_metadata.json', markerMetadata);
  checkSchemaVersion('blocks.geojson', blocks);
  // local-area-boundary.geojson is the City's file passed through unchanged,
  // and overlay_areas.geojson a plain FeatureCollection; neither carries a
  // schema_version.
  return {
    filterConfig: filterConfig as FilterConfig,
    markers: (markerMetadata as { markers: MarkerRecord[] }).markers,
    blocks: blocks as BlocksCollection,
    boundaries: boundaries as BoundaryCollection,
    overlays: overlays as OverlayCollection,
  };
}

export async function loadBuildingArtifacts(): Promise<BuildingArtifacts> {
  const [buildingData, networks] = await Promise.all([
    fetchJson('building_records.json'),
    fetchJson('networks.json'),
  ]);
  checkSchemaVersion('building_records.json', buildingData);
  checkSchemaVersion('networks.json', networks);
  return buildingViews(buildingData as BuildingRecordsFile, networks as NetworksFile);
}
