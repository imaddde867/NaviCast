import assert from 'node:assert/strict';
import { test } from 'node:test';
import { randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { archiveKey, collectMetadata, collectSnapshot, metaKey, MAX_BODY_BYTES, MAX_RETENTION_DAYS } from '../cloudflare/collector.mjs';
import worker, { loadRawSnapshot, loadVesselMetadata, METADATA_CRON, SNAPSHOT_CRON } from '../cloudflare/worker.mjs';
import { fakeD1 } from './fake_d1.mjs';

const NOW = Date.UTC(2026, 9, 13, 8, 5, 42, 123);
const SEEN = Date.now();
const feature = (mmsi, properties = {}, coordinates = [24, 60]) => ({
  type: 'Feature', geometry: { type: 'Point', coordinates },
  properties: { mmsi, sog: 8, cog: 90, navStat: 0, rot: 0, posAcc: true, raim: false,
    heading: 90, timestamp: 10, timestampExternal: SEEN - 90_000, ...properties },
});

function setup(t, features, upstream, d1Options) {
  const fetches = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    fetches.push({ url: String(url), options });
    return upstream ? upstream() : Response.json({ type: 'FeatureCollection', dataUpdatedTime: '2026-10-13T08:05:40Z', features });
  });
  const db = fakeD1(d1Options);
  return { env: { AIS_ARCHIVE_DB: db }, db, fetches };
}
const gunzipText = body => gunzipSync(Buffer.from(body)).toString();
const lines = body => gunzipText(body).trimEnd().split('\n').map(line => JSON.parse(line));
const inserts = db => db.queries.filter(q => q.sql.startsWith('INSERT'));
const quiet = t => t.mock.method(console, 'error', () => {});
const vessel = (mmsi, extra = {}) => ({ mmsi, name: 'FIXTURE', callSign: 'OHXX', imo: 1000001, shipType: 70,
  destination: 'HELSINKI', draught: 45, eta: 123456, timestamp: 1, ...extra });
const metaLoader = vessels => async () => ({ fetched_at: NOW, source: 'https://fixture.test/vessels', updated_at: null, vessels });

test('archiveKey and metaKey are UTC', () => {
  assert.equal(archiveKey(NOW), 'ais/2026/10/13/08/05.ndjson.gz');
  assert.equal(archiveKey(Date.UTC(2026, 0, 2, 23, 59, 59)), 'ais/2026/01/02/23/59.ndjson.gz');
  assert.equal(metaKey(NOW), 'meta/2026/10/13.json.gz');
});

test('inserts one gzipped NDJSON row with header and raw sentinel values', async t => {
  const { env, db, fetches } = setup(t, [
    feature(230000001),
    feature(230000002, { sog: 102.3, cog: 360, heading: 511, rot: -128, navStat: 15, timestampExternal: SEEN - 40 * 60_000 }, [25.5, 59.9]),
    feature(0), feature(1000000000), feature(230000003, {}, [181, 60]),
    feature(230000004, {}, [24, -91]), feature(230000005, {}, [24, Infinity]),
    { type: 'Feature', geometry: null, properties: { mmsi: 1 } },
  ]);
  const result = await collectSnapshot(env, NOW, loadRawSnapshot);
  assert.equal(result.ok, true);
  assert.equal(result.count, 2);
  assert.equal(fetches[0].options.headers['Digitraffic-User'], 'NaviCast/imadlab.com');
  assert.equal(db.rows.size, 1);
  const row = db.rows.get('ais/2026/10/13/08/05.ndjson.gz');
  assert.ok(row.body instanceof ArrayBuffer, 'body is bound as an ArrayBuffer');
  assert.deepEqual([row.kind, row.scheduled_at, row.count, row.data_updated_at],
    ['ais', NOW, 2, '2026-10-13T08:05:40Z']);
  assert.ok(Number.isFinite(row.fetched_at));
  const [header, a, b, ...rest] = lines(row.body);
  assert.equal(rest.length, 0);
  assert.equal(header.schema, 1);
  assert.equal(header.count, 2);
  assert.equal(header.fetched_at, new Date(row.fetched_at).toISOString());
  assert.match(header.source, /digitraffic/);
  assert.equal(a.mmsi, 230000001);
  assert.deepEqual([a.lat, a.lon, a.sog, a.cog, a.heading, a.rot, a.posAcc, a.raim], [60, 24, 8, 90, 90, 0, true, false]);
  assert.equal(a.timestampExternal, SEEN - 90_000);
  assert.ok(Math.abs(a.age_s - 90) < 5);
  assert.deepEqual([b.sog, b.cog, b.heading, b.rot, b.navStat], [102.3, 360, 511, -128, 15]);
  assert.ok(b.age_s > 30 * 60, 'stale observations are kept, with age_s');
});

test('a retry in the same minute is a no-op and keeps the first row', async t => {
  const { env, db } = setup(t, [feature(230000001)]);
  assert.equal((await collectSnapshot(env, NOW, loadRawSnapshot)).ok, true);
  const first = db.rows.get('ais/2026/10/13/08/05.ndjson.gz');
  assert.equal((await collectSnapshot(env, NOW + 10_000, loadRawSnapshot)).ok, true);
  assert.equal(inserts(db).length, 2);
  assert.equal(db.rows.size, 1);
  assert.equal(db.rows.get(first.key), first);
});

test('accepts an injected snapshot loader', async t => {
  const { env, db, fetches } = setup(t, []);
  const loader = async () => ({ fetched_at: NOW, source: 'https://fixture.test/ais', features: [feature(230000009)] });
  assert.equal((await collectSnapshot(env, NOW, loader)).count, 1);
  assert.equal(lines([...db.rows.values()][0].body)[0].source, 'https://fixture.test/ais');
  assert.equal(fetches.length, 0);
});

test('requires source provenance and a finite scheduled timestamp', async t => {
  const { env } = setup(t, []);
  const featureLoader = async () => ({ fetched_at: NOW, source: 'fixture', features: [feature(230000009)] });
  const missingSource = async () => ({ fetched_at: NOW, features: [feature(230000009)] });
  quiet(t);
  await assert.rejects(collectSnapshot(env, NOW, missingSource), /source missing/);
  await assert.rejects(collectSnapshot(env, undefined, featureLoader), /Invalid scheduled timestamp/);
  assert.equal((await collectSnapshot(env, 0, featureLoader)).key, 'ais/1970/01/01/00/00.ndjson.gz');
});

test('upstream failures reject and write nothing', async t => {
  quiet(t);
  for (const upstream of [() => new Response('nope', { status: 503 }), () => new Response('not json'),
    () => Response.json({ type: 'Other' }), () => { throw new Error('network down'); }]) {
    const { env, db } = setup(t, [], upstream);
    await assert.rejects(collectSnapshot(env, NOW, loadRawSnapshot));
    assert.equal(inserts(db).length, 0);
  }
});

test('D1 errors and a missing binding are thrown, not swallowed', async t => {
  quiet(t);
  const { env } = setup(t, [feature(230000001)], undefined, { fail: new Error('D1 down') });
  await assert.rejects(collectSnapshot(env, NOW, loadRawSnapshot), /D1 down/);
  await assert.rejects(collectSnapshot({}, NOW, loadRawSnapshot), /binding missing/);
});

const DAY_MS = 86_400_000;
const seed = (db, key, kind = key.startsWith('ais') ? 'ais' : 'meta') => db.rows.set(key, { key, kind, fetched_at: 1 });

test('pauses when the oldest AIS row is more than the retention age, without fetching or writing', async t => {
  quiet(t);
  const old = setup(t, [feature(230000001)]);
  seed(old.db, archiveKey(NOW - MAX_RETENTION_DAYS * DAY_MS - 60_000));
  seed(old.db, archiveKey(NOW - 60_000));
  const message = /archive paused: retention exceeded, download and clean up/;
  await assert.rejects(collectSnapshot(old.env, NOW, loadRawSnapshot), message);
  await assert.rejects(collectMetadata(old.env, NOW, metaLoader([vessel(230000001)])), message);
  assert.equal(inserts(old.db).length, 0);
  assert.equal(old.fetches.length, 0);
  assert.equal(old.db.queries.filter(q => q.sql.startsWith('SELECT key')).length, 2, 'one indexed row per run');
});

test('exactly the retention age, a newer oldest row, an empty table and old meta rows do not pause', async t => {
  const edge = setup(t, [feature(230000001)]);
  const minute = Math.floor(NOW / 60_000) * 60_000; // real cron scheduledTime is on the minute
  seed(edge.db, archiveKey(minute - MAX_RETENTION_DAYS * DAY_MS));
  assert.equal((await collectSnapshot(edge.env, minute, loadRawSnapshot)).ok, true);
  const metaOnly = setup(t, [feature(230000001)]);
  seed(metaOnly.db, metaKey(NOW - 30 * DAY_MS));
  assert.equal((await collectSnapshot(metaOnly.env, NOW, loadRawSnapshot)).ok, true);
  const empty = setup(t, [feature(230000001)]);
  assert.equal((await collectSnapshot(empty.env, NOW, loadRawSnapshot)).ok, true);
  assert.deepEqual(empty.db.queries.map(q => q.sql.split(' ')[0]), ['SELECT', 'INSERT']);
});

test('timestampExternal must be an integer, and data_updated_at is a string or null in header and row', async t => {
  const { env, db } = setup(t, []);
  const loader = updated => async () => ({ fetched_at: NOW, source: 'fixture', updated_at: updated, features: [
    feature(230000001, { timestampExternal: 1.5 }), feature(230000002, { timestampExternal: '1760000000000' }),
    feature(230000003, { timestampExternal: SEEN }),
  ] });
  await collectSnapshot(env, NOW, loader(12345));
  const row = db.rows.get(archiveKey(NOW));
  const [header, a, b, c] = lines(row.body);
  assert.deepEqual([a.timestampExternal, a.age_s, b.timestampExternal, b.age_s, c.timestampExternal], [null, null, null, null, SEEN]);
  // A numeric epoch is stored as ISO so /health's Date.parse can read it.
  assert.deepEqual([header.data_updated_at, row.data_updated_at], ['1970-01-01T00:00:12.345Z', '1970-01-01T00:00:12.345Z']);
  db.rows.clear();
  await collectSnapshot(env, NOW, loader(undefined));
  assert.deepEqual([lines(db.rows.get(archiveKey(NOW)).body)[0].data_updated_at, db.rows.get(archiveKey(NOW)).data_updated_at], [null, null]);
});

test('rejects bodies over the D1 row cap and writes nothing', async t => {
  quiet(t);
  const { env, db } = setup(t, []);
  // Random hex does not compress below ~50%, so this gzip body exceeds MAX_BODY_BYTES.
  const noisy = Array.from({ length: 30000 }, () => vessel(230000001, { name: randomBytes(32).toString('hex') }));
  await assert.rejects(collectMetadata(env, NOW, metaLoader(noisy)), /Archive body too large/);
  assert.equal(inserts(db).length, 0);
  assert.equal(MAX_BODY_BYTES, 900_000);
});

test('collectMetadata archives vessels without lat/lon as one wrapped JSON row', async t => {
  const { env, db } = setup(t, []);
  const vessels = [vessel(230000001), vessel(230000002, { name: null }), vessel(0), vessel(1000000000),
    vessel(23.5), { name: 'no mmsi' }, null];
  const result = await collectMetadata(env, NOW, metaLoader(vessels));
  assert.deepEqual([result.ok, result.key, result.count], [true, 'meta/2026/10/13.json.gz', 2]);
  const row = db.rows.get('meta/2026/10/13.json.gz');
  assert.deepEqual([row.kind, row.scheduled_at, row.fetched_at, row.data_updated_at, row.count], ['meta', NOW, NOW, null, 2]);
  const wrapper = JSON.parse(gunzipText(row.body));
  assert.deepEqual([wrapper.schema, wrapper.source, wrapper.fetched_at, wrapper.count],
    [1, 'https://fixture.test/vessels', new Date(NOW).toISOString(), 2]);
  assert.deepEqual(wrapper.vessels.map(v => v.mmsi), [230000001, 230000002]);
  assert.equal(wrapper.vessels[0].destination, 'HELSINKI');
  assert.ok(!('lat' in wrapper.vessels[0]));
  assert.equal((await collectMetadata(env, NOW + 1000, metaLoader(vessels))).ok, true);
  assert.equal(db.rows.size, 1, 'same day is idempotent');
});

test('collectMetadata rejects empty metadata and a missing source', async t => {
  quiet(t);
  const { env, db } = setup(t, []);
  await assert.rejects(collectMetadata(env, NOW, metaLoader([vessel(0)])), /Empty metadata/);
  await assert.rejects(collectMetadata(env, NOW, async () => ({ fetched_at: NOW, vessels: [vessel(1)] })), /source missing/);
  assert.equal(inserts(db).length, 0);
});

test('loadVesselMetadata fetches the vessels feed and validates the array shape', async t => {
  const list = [vessel(230000001)];
  const responses = [Response.json(list), Response.json({ type: 'FeatureCollection' }), new Response('down', { status: 503 })];
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => { calls.push({ url: String(url), options }); return responses.shift(); });
  const snap = await loadVesselMetadata();
  assert.deepEqual(snap.vessels, list);
  assert.equal(snap.source, 'https://meri.digitraffic.fi/api/ais/v1/vessels');
  assert.equal(calls[0].url, snap.source);
  assert.equal(calls[0].options.headers['Digitraffic-User'], 'NaviCast/imadlab.com');
  assert.equal(calls[0].options.redirect, 'manual');
  await assert.rejects(loadVesselMetadata(), /Invalid upstream schema/);
  await assert.rejects(loadVesselMetadata(), /Invalid upstream response/);
});

test('scheduled dispatches the minute cron to AIS and the daily cron to metadata', async t => {
  const { env, db, fetches } = setup(t, [feature(230000001)], undefined);
  assert.equal((await worker.scheduled({ cron: SNAPSHOT_CRON, scheduledTime: NOW }, env)).key, 'ais/2026/10/13/08/05.ndjson.gz');
  assert.equal(fetches.at(-1).url, 'https://meri.digitraffic.fi/api/ais/v1/locations');
  t.mock.method(globalThis, 'fetch', async url => {
    fetches.push({ url: String(url) });
    return Response.json([vessel(230000001)]);
  });
  assert.equal((await worker.scheduled({ cron: METADATA_CRON, scheduledTime: NOW }, env)).key, 'meta/2026/10/13.json.gz');
  assert.equal(fetches.at(-1).url, 'https://meri.digitraffic.fi/api/ais/v1/vessels');
  assert.deepEqual([...db.rows.values()].map(r => r.kind), ['ais', 'meta']);
});

test('scheduled rejects so the cron run is marked failed', async t => {
  quiet(t);
  const upstreamDown = setup(t, [], () => new Response('unavailable', { status: 503 }));
  await assert.rejects(worker.scheduled({ cron: '* * * * *', scheduledTime: NOW }, upstreamDown.env), /Invalid upstream response/);
  const { env, db } = setup(t, [feature(230000001)]);
  await assert.rejects(worker.scheduled({ cron: '* * * * *' }, env), /Invalid scheduled timestamp/);
  assert.equal(inserts(db).length, 0);
  const metaDown = setup(t, [], () => new Response('unavailable', { status: 503 }));
  await assert.rejects(worker.scheduled({ cron: '10 0 * * *', scheduledTime: NOW }, metaDown.env), /Invalid upstream response/);
  const paused = setup(t, [feature(230000001)]);
  seed(paused.db, archiveKey(NOW - (MAX_RETENTION_DAYS + 1) * DAY_MS));
  await assert.rejects(worker.scheduled({ cron: '* * * * *', scheduledTime: NOW }, paused.env), /retention exceeded/);
});

test('scheduled throws on an unknown cron and does no work', async t => {
  quiet(t);
  const { env, db, fetches } = setup(t, [feature(230000001)]);
  for (const cron of ['*/5 * * * *', undefined, '']) {
    await assert.rejects(worker.scheduled({ cron, scheduledTime: NOW }, env), /Unknown cron/);
  }
  assert.equal(fetches.length + db.queries.length, 0);
});

test('worker cron constants match wrangler.jsonc triggers', () => {
  const config = readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const crons = JSON.parse(/"crons":\s*(\[[^\]]*\])/.exec(config)[1]);
  assert.deepEqual(crons, [SNAPSHOT_CRON, METADATA_CRON]);
});
