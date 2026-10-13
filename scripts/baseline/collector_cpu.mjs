// LOCAL CPU PROBE (Node on a development machine), not Cloudflare Workers CPU accounting and not proof
// of any per-invocation CPU budget. It runs the real collectors against a fake in-memory D1 binding and
// raw feed files; network, real D1 latency and the Workers runtime are not part of the measurement.
// Usage: node scripts/baseline/collector_cpu.mjs <collector.mjs> <raw-locations.json> [raw-vessels.json]
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { gunzipSync } from 'node:zlib';

assert(process.argv[2] && process.argv[3], 'Pass the collector module and a raw Digitraffic locations snapshot');
const { collectSnapshot, collectMetadata } = await import(pathToFileURL(resolve(process.argv[2])));
let compressed;
// Fake D1: the retention check (prepare().first()) and insert (prepare().bind().run()).
const env = {
  AIS_ARCHIVE_DB: {
    prepare: sql => ({
      first: async () => null,
      bind: (...args) => ({
        async run() {
          if (sql.startsWith('INSERT')) compressed = Buffer.from(args[6]);
          return { meta: { changes: 1 } };
        },
      }),
    }),
  },
};
const p95 = values => [...values].sort((a, b) => a - b)[Math.ceil(values.length * 0.95) - 1];

async function probe(path, collect, loaderFor, expectRecords) {
  const raw = readFileSync(path);
  const cpu = [], wall = [];
  let result;
  for (let i = 0; i < 55; i++) {
    const usage = process.cpuUsage();
    const start = performance.now();
    result = await collect(env, Date.now(), loaderFor(raw));
    const elapsed = performance.now() - start;
    const used = process.cpuUsage(usage);
    assert.equal(result.ok, true);
    if (i >= 5) { cpu.push((used.user + used.system) / 1000); wall.push(elapsed); }
  }
  assert(result.count > 0);
  expectRecords(gunzipSync(compressed).toString('utf8'), result.count);
  return {
    fixture_sha256: createHash('sha256').update(raw).digest('hex'), raw_bytes: raw.length,
    gzip_bytes: compressed.length, records: result.count, samples: cpu.length,
    p95_process_cpu_ms: p95(cpu), p95_wall_ms: p95(wall),
  };
}

const snapshot = await probe(process.argv[3], collectSnapshot, raw => async () => {
  const payload = JSON.parse(raw.toString('utf8'));
  assert.equal(payload.type, 'FeatureCollection');
  return {
    fetched_at: Date.now(), source: 'local fixture (not fetched)',
    updated_at: payload.dataUpdatedTime ?? null, features: payload.features,
  };
}, (text, count) => {
  const lines = text.trim().split('\n').map(JSON.parse);
  assert.equal(lines[0].count, lines.length - 1);
  assert.equal(count, lines.length - 1);
});

const metadata = process.argv[4] && await probe(process.argv[4], collectMetadata, raw => async () => {
  const vessels = JSON.parse(raw.toString('utf8'));
  assert(Array.isArray(vessels));
  return { fetched_at: Date.now(), source: 'local fixture (not fetched)', updated_at: null, vessels };
}, (text, count) => {
  const wrapper = JSON.parse(text);
  assert.equal(wrapper.count, wrapper.vessels.length);
  assert.equal(count, wrapper.vessels.length);
});

console.log(JSON.stringify({
  measured_at: new Date().toISOString(), runtime: process.version, platform: process.platform,
  snapshot_cron: snapshot,
  metadata_cron: metadata || 'not probed (no vessels fixture passed)',
  method: 'Warm local Node parse + serialization + CompressionStream + fake in-memory D1 insert; 50 samples after 5 warm-up runs',
  limitation: 'Node process CPU includes compression worker threads; not Cloudflare Workers CPU accounting. Nothing is deployed; real Workers CPU time for both crons is unmeasured.',
}, null, 2));
