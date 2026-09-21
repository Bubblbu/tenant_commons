// frontend/artifacts-plugin.test.ts
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { resolveArtifactPath } from './artifacts-plugin';

const DIR = resolve('/srv/artifacts');

describe('resolveArtifactPath', () => {
  it('maps a request path into the artifact directory', () => {
    expect(resolveArtifactPath(DIR, '/marker_metadata.json')).toBe(resolve(DIR, 'marker_metadata.json'));
  });

  it('ignores the query string', () => {
    expect(resolveArtifactPath(DIR, '/blocks.geojson?v=2')).toBe(resolve(DIR, 'blocks.geojson'));
  });

  it('refuses to escape the directory', () => {
    expect(resolveArtifactPath(DIR, '/../secret.json')).toBeNull();
    expect(resolveArtifactPath(DIR, '/%2e%2e/secret.json')).toBeNull();
  });

  it('refuses the directory itself', () => {
    expect(resolveArtifactPath(DIR, '/')).toBeNull();
  });

  it('returns null for malformed percent-encoding instead of throwing', () => {
    expect(resolveArtifactPath(DIR, '/%E0')).toBeNull();
  });
});
