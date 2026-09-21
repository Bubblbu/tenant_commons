/**
 * The artifact directory is the frontend's only input (spec §3). Under
 * `npm run dev` it is served at /data/; `npm run build` copies it into
 * dist/data/. Which directory is a single setting, SICA_ARTIFACTS_DIR,
 * resolved in vite.config.ts.
 */
import { cpSync, createReadStream, existsSync, statSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import type { Plugin } from 'vite';

/** Absolute path for a /data/ request, or null if it escapes `dir`, names `dir` itself, or is malformed. */
export function resolveArtifactPath(dir: string, url: string): string | null {
  let rel: string;
  try {
    rel = decodeURIComponent(url.split('?')[0]);
  } catch {
    return null; // malformed percent-encoding, e.g. /%E0 (decodeURIComponent throws URIError)
  }
  const file = resolve(dir, '.' + rel);
  return file.startsWith(dir + sep) ? file : null;
}

function requireDir(dir: string): void {
  if (!existsSync(dir) || !statSync(dir).isDirectory()) {
    throw new Error(
      `Artifact directory not found: ${dir}\n` +
        'Run `uv run python scripts/rebuild_map.py` from the repo root, ' +
        'or point SICA_ARTIFACTS_DIR at an artifact directory (e.g. SICA_ARTIFACTS_DIR=fixtures).',
    );
  }
}

export function sicaArtifacts(dir: string): Plugin {
  let outDir = '';
  let command: 'build' | 'serve' = 'serve';
  return {
    name: 'sica-artifacts',
    configResolved(config) {
      command = config.command;
      outDir = resolve(config.root, config.build.outDir);
    },
    buildStart() {
      // Only a build needs the directory. Vite's dev server (which Vitest
      // also runs) calls buildStart too, and tests must not depend on it.
      if (command === 'build') requireDir(dir);
    },
    configureServer(server) {
      if (!process.env.VITEST && !existsSync(dir)) {
        server.config.logger.warn(
          `Artifact directory not found: ${dir} — the map will show a load error. ` +
            'Run `uv run python scripts/rebuild_map.py` from the repo root, or set SICA_ARTIFACTS_DIR.',
        );
      }
      server.middlewares.use('/data', (req, res, next) => {
        const file = resolveArtifactPath(dir, req.url ?? '/');
        if (!file || !existsSync(file) || !statSync(file).isFile()) return next();
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        createReadStream(file).pipe(res);
      });
    },
    writeBundle() {
      cpSync(dir, resolve(outDir, 'data'), { recursive: true });
    },
  };
}
