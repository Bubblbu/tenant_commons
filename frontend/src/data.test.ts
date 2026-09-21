import { describe, expect, it } from 'vitest';
import { ArtifactError, checkSchemaVersion } from './data';

describe('checkSchemaVersion', () => {
  it('accepts the expected version', () => {
    expect(() => checkSchemaVersion('marker_metadata.json', { schema_version: 1, markers: [] })).not.toThrow();
  });

  it('rejects a different version, naming the file', () => {
    expect(() => checkSchemaVersion('blocks.geojson', { schema_version: 2 })).toThrow(ArtifactError);
    expect(() => checkSchemaVersion('blocks.geojson', { schema_version: 2 })).toThrow(/blocks\.geojson/);
  });

  it('rejects a payload with no version (e.g. a pre-contract file)', () => {
    expect(() => checkSchemaVersion('filter_config.json', {})).toThrow(ArtifactError);
    expect(() => checkSchemaVersion('filter_config.json', [])).toThrow(ArtifactError);
  });
});
