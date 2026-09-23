import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import { tcArtifacts } from './artifacts-plugin.ts';

const HERE = fileURLToPath(new URL('.', import.meta.url));
// Relative values resolve against the current directory (frontend/ under npm).
const ARTIFACTS_DIR = resolve(
  process.env.TC_ARTIFACTS_DIR ?? resolve(HERE, '../data/derived/artifacts'),
);

export default defineConfig({
  // Relative asset and artifact URLs, so dist/ works from any path (e.g. a Pages subpath).
  base: './',
  plugins: [tcArtifacts(ARTIFACTS_DIR)],
  test: { environment: 'node' },
});
