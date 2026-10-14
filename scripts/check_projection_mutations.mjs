// Targeted mutation evidence; production sources are copied, never edited.
import assert from 'node:assert/strict';
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const original = readFileSync(join(root, 'cloudflare/worker.mjs'), 'utf8');
const mutations = [
  ['invalid speed allowed', 'const sog = motion(properties.sog, 102.3);', 'const sog = motion(properties.sog, 102.3) ?? 8;'],
  ['31 minute horizon', 'const HORIZON_MS = 30 * 60 * 1000;', 'const HORIZON_MS = 31 * 60 * 1000;'],
  ['land conflict suppressed', 'projection_land_conflict: conflict,', 'projection_land_conflict: false,'],
  ['null projection fabricated', 'predicted_latitude: null,', 'predicted_latitude: lat,'],
];
const temporary = mkdtempSync(join(tmpdir(), 'navicast-mutations-'));
try {
  cpSync(join(root, 'cloudflare'), join(temporary, 'cloudflare'), { recursive: true });
  mkdirSync(join(temporary, 'tests'));
  for (const path of ['golden.test.mjs', 'fixtures', 'golden']) {
    cpSync(join(root, 'tests', path), join(temporary, 'tests', path), { recursive: true });
  }
  const run = () => {
    const result = spawnSync(process.execPath, ['--test', 'tests/golden.test.mjs'], {
      cwd: temporary, encoding: 'utf8', timeout: 30_000,
    });
    assert.ifError(result.error);
    assert.match(result.stdout, /# tests 3\b/, 'golden suite must actually execute');
    return result;
  };
  assert.equal(run().status, 0, 'unmutated copy must pass');
  for (const [name, before, after] of mutations) {
    assert.equal(original.split(before).length, 2, `${name}: exactly one mutation site`);
    writeFileSync(join(temporary, 'cloudflare/worker.mjs'), original.replace(before, after));
    const result = run();
    assert.notEqual(result.status, 0, `${name}: mutation survived`);
    assert.match(result.stdout, /# fail [1-9]/, `${name}: must fail assertions, not startup`);
    console.log(`DETECTED: ${name}`);
  }
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
