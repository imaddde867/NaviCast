// Local CPU probe, not proof of Cloudflare's per-invocation CPU budget.
// Usage: node scripts/baseline/collector_cpu.mjs <collector.mjs> <raw-locations.json>
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { gunzipSync } from 'node:zlib';

assert(process.argv[2] && process.argv[3], 'Pass the collector module and a raw Digitraffic locations snapshot');
const { collectSnapshot } = await import(pathToFileURL(resolve(process.argv[2])));
const raw = readFileSync(process.argv[3]);
const cpu = [], wall = [];
let compressed;
const env = { AIS_ARCHIVE: { async put(key, body) { compressed = Buffer.from(body); } } };
const loader = async () => {
  const payload = JSON.parse(raw.toString('utf8'));
  assert.equal(payload.type, 'FeatureCollection');
  return { fetched_at: Date.now(), updated_at: payload.dataUpdatedTime ?? null, features: payload.features };
};
let result;
for (let i = 0; i < 55; i++) {
  const usage = process.cpuUsage();
  const start = performance.now();
  result = await collectSnapshot(env, Date.now(), loader);
  const elapsed = performance.now() - start;
  const used = process.cpuUsage(usage);
  assert.equal(result.ok, true, result.error);
  if (i >= 5) { cpu.push((used.user + used.system) / 1000); wall.push(elapsed); }
}
const lines = gunzipSync(compressed).toString('utf8').trim().split('\n').map(JSON.parse);
assert.equal(lines[0].count, lines.length - 1);
assert.equal(result.count, lines.length - 1);
assert(result.count > 0);
const p95 = values => values.sort((a, b) => a - b)[Math.ceil(values.length * 0.95) - 1];
console.log(JSON.stringify({
  measured_at: new Date().toISOString(), runtime: process.version, platform: process.platform,
  fixture_sha256: createHash('sha256').update(raw).digest('hex'), raw_bytes: raw.length,
  gzip_bytes: compressed.length, records: result.count, samples: cpu.length,
  p95_process_cpu_ms: p95(cpu), p95_wall_ms: p95(wall),
  method: 'Warm local Node parse + record serialization + CompressionStream + in-memory put; excludes network and R2',
  limitation: 'Node process CPU includes compression worker threads; not Cloudflare Workers CPU accounting. Verify both minute and daily metadata crons after owner deploy.',
}, null, 2));
