// Demonstrate E2E regression sensitivity without touching the working dashboard.
import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const html = readFileSync(join(root, 'static/index.html'), 'utf8');
const mutations = [
  ['render notice removed', '<div id="render-notice" role="status" aria-live="polite" hidden></div>', ''],
  ['API request cap broken', "fetch('/vessels?limit=1000'", "fetch('/vessels?limit=500'"],
  ['browser projection fallback', 'return { predictedPos: null };', 'return { predictedPos: [data.current_latitude + 0.1, data.current_longitude] };'],
];
const temporary = mkdtempSync(join(tmpdir(), 'navicast-browser-mutations-'));
try {
  for (const path of ['static', 'tests/browser', 'playwright.config.mjs']) {
    cpSync(join(root, path), join(temporary, path), { recursive: true });
  }
  symlinkSync(join(root, 'node_modules'), join(temporary, 'node_modules'), 'dir');
  const run = () => {
    const result = spawnSync(process.execPath, [join(root, 'node_modules/playwright/cli.js'),
      'test', '--grep', 'missing projection|600 API records'], { cwd: temporary, encoding: 'utf8', timeout: 60_000 });
    assert.ifError(result.error);
    assert.match(result.stdout, /Running 2 tests/, 'real browser tests must execute');
    return result;
  };
  assert.equal(run().status, 0, 'baseline browser copy must pass');
  for (const [name, before, after] of mutations) {
    assert.equal(html.split(before).length, 2, `${name}: exactly one site`);
    writeFileSync(join(temporary, 'static/index.html'), html.replace(before, after));
    const result = run();
    assert.notEqual(result.status, 0, `${name}: survived`);
    assert.match(result.stdout, /[1-9] failed/, `${name}: must fail executed assertions`);
    console.log(`DETECTED: ${name}`);
  }
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
