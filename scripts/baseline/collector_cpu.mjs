// LOCAL CPU PROBE, not Cloudflare Workers CPU accounting and not proof of any per-invocation CPU budget.
// It runs the real collectSnapshot against a fake in-memory D1 binding and a raw feed file.
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
// Fake D1: the collector's size check (prepare().run()) and insert (prepare().bind().run()).
const statement = sql => ({
  run: async () => ({ meta: { size_after: 0, changes: 1 } }),
  bind: (...args) => ({
    async run() {
      if (sql.startsWith('INSERT')) compressed = Buffer.from(args[6]);
      return { meta: { size_after: 0, changes: 1 } };
    },
  }),
});
const env = { AIS_ARCHIVE_DB: { prepare: statement } };
const loader = async () => {
  const payload = JSON.parse(raw.toString('utf8'));
  assert.equal(payload.type, 'FeatureCollection');
  return {
    fetched_at: Date.now(), source: 'local fixture (not fetched)',
    updated_at: payload.dataUpdatedTime ?? null, features: payload.features,
  };
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
  method: 'Warm local Node parse + record serialization + CompressionStream + fake in-memory D1 insert; excludes network and real D1 latency; snapshot cron only, daily metadata cron not measured',
  limitation: 'Node process CPU includes compression worker threads; not Cloudflare Workers CPU accounting. Nothing is deployed; real Workers CPU time for both crons is unmeasured.',
}, null, 2));
