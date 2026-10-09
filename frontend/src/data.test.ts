import { describe, expect, it } from 'vitest';
import { ArtifactError, buildingViews, checkSchemaVersion } from './data';
import type { Building, Network } from './contract.gen';
import { FLAT_COLUMNS } from './flat';

describe('checkSchemaVersion', () => {
  it('accepts the expected version', () => {
    expect(() => checkSchemaVersion('marker_metadata.json', { schema_version: 2, markers: [] })).not.toThrow();
  });

  it('rejects a different version, naming the file', () => {
    expect(() => checkSchemaVersion('blocks.geojson', { schema_version: 1 })).toThrow(ArtifactError);
    expect(() => checkSchemaVersion('blocks.geojson', { schema_version: 1 })).toThrow(/blocks\.geojson/);
  });

  it('rejects a payload with no version (e.g. a pre-contract file)', () => {
    expect(() => checkSchemaVersion('filter_config.json', {})).toThrow(ArtifactError);
    expect(() => checkSchemaVersion('filter_config.json', [])).toThrow(ArtifactError);
  });
});

describe('buildingViews', () => {
  it('keeps the nested buildings for the popup and a flat view for the tables', () => {
    const b: Building = {
      id: 7, origin: 'building', address: '1 main st', name: null, also_known_as: [], pids: [], local_area: 'X',
      block_id: null, lat: 49.2, lon: -123.1, in_chinatown: false, in_village_plan: false, units: 5,
      units_basis: 'inventory', year_built: 1950, listed_in: [], value: null, issues: null, parties: [],
      network_id: 'n1', registry_search: { status: 'not_searched', date: null }, coop: null, sro: null, rezoning: null,
    };
    const n1: Network = { id: 'n1', name: 'N', name_source: 'default', tier: 'name_match',
      evidence: { registry: 0, city_records: 0, vtu_research: 0 }, entities: [],
      totals: { buildings: 1, units: 5, open_issues: 0, properties_on_title: null } };
    const views = buildingViews(
      { schema_version: 2, records: { '7': b } },
      { schema_version: 2, networks: { n1 } },
    );
    expect(views.buildings['7']).toBe(b);
    expect(views.networks.n1).toBe(n1);
    expect(views.buildingData.columns).toEqual(FLAT_COLUMNS);
    expect(views.buildingData.records['7'].network_name).toBe('N');
  });
});
