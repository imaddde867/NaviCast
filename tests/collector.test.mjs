import assert from 'node:assert/strict';
import { test } from 'node:test';
import { gunzipSync } from 'node:zlib';
import { archiveKey, collectSnapshot } from '../cloudflare/collector.mjs';
import worker from '../cloudflare/worker.mjs';

const NOW = Date.UTC(2026, 9, 13, 8, 5, 42, 123);
const SEEN = Date.now();
const feature = (mmsi, properties = {}, coordinates = [24, 60]) => ({
  type: 'Feature', geometry: { type: 'Point', coordinates },
  properties: { mmsi, sog: 8, cog: 90, navStat: 0, rot: 0, posAcc: true, raim: false,
    heading: 90, timestamp: 10, timestampExternal: SEEN - 90_000, ...properties },
});

function setup(t, features, upstream) {
  const puts = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    puts.push({ fetch: String(url), options });
    return upstream ? upstream() : Response.json({ type: 'FeatureCollection', dataUpdatedTime: '2026-10-13T08:05:40Z', features });
  });
  const env = { AIS_ARCHIVE: { async put(key, body, options) { puts.push({ key, body, options }); } } };
  return { env, puts };
}
const lines = body => gunzipSync(Buffer.from(body)).toString().trimEnd().split('\n').map(line => JSON.parse(line));

test('archiveKey is UTC and minute-granular', () => {
  assert.equal(archiveKey(NOW), 'ais/2026/10/13/08/05.ndjson.gz');
  assert.equal(archiveKey(Date.UTC(2026, 0, 2, 23, 59, 59)), 'ais/2026/01/02/23/59.ndjson.gz');
});

test('writes one gzipped NDJSON object with header and raw sentinel values', async t => {
  const { env, puts } = setup(t, [
    feature(230000001),
    feature(230000002, { sog: 102.3, cog: 360, heading: 511, rot: -128, navStat: 15, timestampExternal: SEEN - 40 * 60_000 }, [25.5, 59.9]),
    { type: 'Feature', geometry: null, properties: { mmsi: 1 } },
  ]);
  const result = await collectSnapshot(env, NOW);
  assert.equal(result.ok, true);
  const put = puts.find(p => p.key);
  assert.equal(put.key, 'ais/2026/10/13/08/05.ndjson.gz');
  assert.equal(puts[0].options.headers['Digitraffic-User'], 'NaviCast/imadlab.com');
  const [header, a, b, ...rest] = lines(put.body);
  assert.equal(rest.length, 0);
  assert.equal(header.schema, 1);
  assert.equal(header.count, 2);
  assert.match(header.source, /digitraffic/);
  assert.ok(Number.isFinite(Date.parse(header.fetched_at)));
  assert.equal(a.mmsi, 230000001);
  assert.deepEqual([a.lat, a.lon, a.sog, a.cog, a.heading, a.rot, a.posAcc, a.raim], [60, 24, 8, 90, 90, 0, true, false]);
  assert.equal(a.timestampExternal, SEEN - 90_000);
  assert.ok(Math.abs(a.age_s - 90) < 5);
  assert.deepEqual([b.sog, b.cog, b.heading, b.rot, b.navStat], [102.3, 360, 511, -128, 15]);
  assert.ok(b.age_s > 30 * 60, 'stale observations are kept, with age_s');
});

test('same minute maps to the same key', async t => {
  const { env, puts } = setup(t, [feature(230000001)]);
  await collectSnapshot(env, NOW);
  await collectSnapshot(env, NOW + 10_000);
  const keys = puts.filter(p => p.key).map(p => p.key);
  assert.equal(keys.length, 2);
  assert.equal(keys[0], keys[1]);
});

test('accepts an injected snapshot loader', async t => {
  const { env, puts } = setup(t, []);
  const loader = async () => ({ fetched_at: NOW, features: [feature(230000009)] });
  assert.equal((await collectSnapshot(env, NOW, loader)).count, 1);
  assert.equal(puts.filter(p => p.fetch).length, 0);
});

test('failures return ok:false and write nothing', async t => {
  for (const upstream of [() => new Response('nope', { status: 503 }), () => new Response('not json'),
    () => Response.json({ type: 'Other' }), () => { throw new Error('network down'); }]) {
    const { env, puts } = setup(t, [], upstream);
    t.mock.method(console, 'error', () => {});
    const result = await collectSnapshot(env, NOW);
    assert.equal(result.ok, false);
    assert.equal(typeof result.error, 'string');
    assert.equal(puts.filter(p => p.key).length, 0);
  }
  const failing = { AIS_ARCHIVE: { async put() { throw new Error('R2 down'); } } };
  t.mock.method(globalThis, 'fetch', async () => Response.json({ type: 'FeatureCollection', features: [feature(230000001)] }));
  assert.deepEqual(await collectSnapshot(failing, NOW), { ok: false, error: 'R2 down' });
  assert.equal((await collectSnapshot({}, NOW)).ok, false);
});

test('worker.scheduled delegates to the collector via waitUntil', async t => {
  const { env, puts } = setup(t, [feature(230000001)]);
  const pending = [];
  worker.scheduled({}, env, { waitUntil: p => pending.push(p) });
  assert.equal(pending.length, 1);
  assert.equal((await pending[0]).ok, true);
  assert.equal(puts.filter(p => p.key).length, 1);
});
