import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import { sicaArtifacts } from './artifacts-plugin.ts';

const HERE = fileURLToPath(new URL('.', import.meta.url));
// Relative values resolve against the current directory (frontend/ under npm).
const ARTIFACTS_DIR = resolve(
  process.env.SICA_ARTIFACTS_DIR ?? resolve(HERE, '../data/derived/artifacts'),
);

export default defineConfig({
  // Relative asset and artifact URLs, so dist/ works from any path (e.g. a Pages subpath).
  base: './',
  plugins: [sicaArtifacts(ARTIFACTS_DIR)],
  test: { environment: 'node' },
});
