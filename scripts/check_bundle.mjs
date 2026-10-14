import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';
import { spawnSync } from 'node:child_process';

// Measured main bundle: 561.06 KiB gzip; 600 KiB permits ~39 KiB of reviewed growth.
const budget = 600 * 1024;
const directory = mkdtempSync(join(tmpdir(), 'navicast-bundle-'));
try {
  const result = spawnSync(process.execPath, ['node_modules/wrangler/bin/wrangler.js',
    'deploy', '--dry-run', '--outdir', directory], {
    encoding: 'utf8', timeout: 60_000, env: { ...process.env, WRANGLER_SEND_METRICS: 'false' },
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const modules = readdirSync(directory).filter(name => /\.(m?js|wasm)$/.test(name));
  assert.ok(modules.length, 'bundle must exist');
  const size = modules.reduce((sum, name) => sum + gzipSync(readFileSync(join(directory, name))).length, 0);
  console.log(`Worker gzip bundle: ${size} bytes; budget: ${budget} bytes`);
  assert.ok(size <= budget, `Worker exceeds ${budget}-byte gzip budget`);
} finally {
  rmSync(directory, { recursive: true, force: true });
}
