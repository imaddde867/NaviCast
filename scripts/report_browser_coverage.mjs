import assert from 'node:assert/strict';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import v8ToIstanbul from 'v8-to-istanbul';
import { mergeScriptCovs } from '@bcoe/v8-coverage';

const directory = 'reports/browser-artifacts';
const scripts = [];
let source;
let entries = 0;
const testDirectories = readdirSync(directory, { withFileTypes: true }).filter(entry => entry.isDirectory());
for (const testDirectory of testDirectories) {
  const report = join(directory, testDirectory.name, 'js-coverage.json');
  const before = entries;
  for (const entry of JSON.parse(readFileSync(report, 'utf8'))) {
    if (!entry.url.startsWith('http://127.0.0.1:18765/') || !entry.source?.includes('function determinePrediction')) continue;
    entries++;
    if (source === undefined) source = entry.source;
    assert.equal(entry.source, source, 'all browser cases must measure identical dashboard source');
    scripts.push(entry);
  }
  assert.equal(entries - before, 1, 'every browser scenario must supply dashboard coverage');
}
assert.ok(entries > 0, 'browser coverage must not be empty');
const converter = v8ToIstanbul('static/index.html', 0, { source });
await converter.load();
converter.applyCoverage(mergeScriptCovs(scripts).functions);
const [coverage] = Object.values(converter.toIstanbul());
const statements = Object.values(coverage.s);
const branches = Object.values(coverage.b).flat();
const result = { file: 'static/index.html', tool: 'Chromium V8 / v8-to-istanbul 9.3.0',
  statements: statements.length, missing_statements: statements.filter(n => !n).length,
  branches: branches.length, missing_branches: branches.filter(n => !n).length };
assert.ok(result.statements > 0 && result.branches > 0, 'meaningful coverage must exist');
writeFileSync('reports/browser-coverage.json', JSON.stringify(result, null, 2) + '\n');
console.log(result);
