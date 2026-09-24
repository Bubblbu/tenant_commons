/** Loads the artifact directory once and checks its contract version (spec §4). */
import { EXPECTED_SCHEMA_VERSION, artifactUrl } from './config';
import type {
  Artifacts,
  BlocksCollection,
  BoundaryCollection,
  BuildingData,
  FilterConfig,
  MarkerRecord,
  VillagesCollection,
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

export async function loadArtifacts(): Promise<Artifacts> {
  const [filterConfig, markerMetadata, buildingData, blocks, boundaries, villages, chinatown] = await Promise.all([
    fetchJson('filter_config.json'),
    fetchJson('marker_metadata.json'),
    fetchJson('building_records.json'),
    fetchJson('blocks.geojson'),
    fetchJson('local-area-boundary.geojson'),
    fetchJson('villages_plan_areas.geojson'),
    fetchJson('chinatown_boundary.geojson'),
  ]);
  checkSchemaVersion('filter_config.json', filterConfig);
  checkSchemaVersion('marker_metadata.json', markerMetadata);
  checkSchemaVersion('building_records.json', buildingData);
  checkSchemaVersion('blocks.geojson', blocks);
  // local-area-boundary.geojson, villages_plan_areas.geojson and
  // chinatown_boundary.geojson are passed through unchanged (the City's
  // file; two hand-curated reference layers); none carry a schema_version.
  return {
    filterConfig: filterConfig as FilterConfig,
    markers: (markerMetadata as { markers: MarkerRecord[] }).markers,
    buildingData: buildingData as BuildingData,
    blocks: blocks as BlocksCollection,
    boundaries: boundaries as BoundaryCollection,
    villages: villages as VillagesCollection,
    chinatown: chinatown as BoundaryCollection,
  };
}
