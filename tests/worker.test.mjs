import assert from 'node:assert/strict';
import { test } from 'node:test';
import worker from '../cloudflare/worker.mjs';
import { isLand, pathHitsLand, clearUntilFraction, maskInfo } from '../cloudflare/landmask.mjs';

const now = Date.now();
const sourceTime = now - 60_000;
const iso = value => new Date(value).toISOString();

function feature(mmsi = 230123456, properties = {}, coordinates = [24, 60]) {
  return {
    type: 'Feature', geometry: { type: 'Point', coordinates },
    properties: { mmsi, sog: 8, cog: 90, navStat: 0, posAcc: true,
      heading: 511, timestampExternal: sourceTime, ...properties },
  };
}

function harness(t, features = [feature()], upstream) {
  const entries = new Map();
  const calls = [];
  const pending = [];
  const cache = {
    async match(key) { return entries.get(key.url)?.clone(); },
    async put(key, response) { entries.set(key.url, response.clone()); },
  };
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url: String(url), options });
    return upstream ? upstream(url, options) : Response.json({ type: 'FeatureCollection', features });
  });
  const previousCaches = Object.getOwnPropertyDescriptor(globalThis, 'caches');
  Object.defineProperty(globalThis, 'caches', { configurable: true, value: { default: cache } });
  t.after(() => {
    if (previousCaches) Object.defineProperty(globalThis, 'caches', previousCaches);
    else delete globalThis.caches;
  });
  const env = { ASSETS: { async fetch() { return new Response('static page'); } } };
  const ctx = { waitUntil(promise) { pending.push(promise); } };
  return {
    calls, entries, pending,
    async request(path = '/vessels', method = 'GET') {
      return worker.fetch(new Request(`https://navicast.test${path}`, { method }), env, ctx);
    },
  };
}

test('live vessels preserve source UTC, country, unknown heading, and 30-minute projection', async t => {
  const h = harness(t);
  const response = await h.request();
  assert.equal(response.status, 200);
  const [vessel] = await response.json();
  assert.equal(vessel.vessel_id, 230123456);
  assert.equal(vessel.current_timestamp, iso(sourceTime));
  assert.equal(vessel.current_latitude, 60);
  assert.equal(vessel.current_longitude, 24);
  assert.equal(vessel.country, 'Finland');
  assert.equal(vessel.data_source, 'ais');
  assert.equal(vessel.vessel_type, 'Unknown');
  assert.equal(vessel.vessel_type_code, null);
  assert.equal(vessel.heading, null);
  assert.equal(vessel.vessel_status, 'Under way using engine');
  assert.equal(vessel.pos_acc, true);
  assert.equal(vessel.prediction_method, 'dead_reckoning');
  assert.ok(Math.abs(vessel.predicted_longitude - 24.133343) < 1e-6);
  assert.equal(vessel.predicted_latitude, 60);
  assert.equal(vessel.prediction_for_timestamp, iso(sourceTime + 1_800_000));
  assert.ok(Math.abs(Date.parse(vessel.prediction_made_at) - Date.now()) < 2000);
  assert.equal(h.calls[0].url, 'https://meri.digitraffic.fi/api/ais/v1/locations');
  assert.equal(h.calls[0].options.headers['Accept-Encoding'], 'gzip');
  assert.equal(h.calls[0].options.headers['Digitraffic-User'], 'NaviCast/imadlab.com');
});

test('unknown motion stays null and cannot produce a prediction', async t => {
  const h = harness(t, [feature(230123456, { sog: 102.3, cog: 360, heading: 511, navStat: true, posAcc: 'false' }),
    feature(230123457, { sog: false, cog: '', heading: {}, navStat: 2.5, posAcc: false }),
    feature(230123458, { sog: '0x10', cog: '0x20', heading: '0x30', navStat: '0x0', posAcc: false })]);
  const response = await h.request();
  assert.equal(response.status, 200);
  const vessels = await response.json();
  assert.equal(vessels.length, 3);
  for (const vessel of vessels) {
    for (const key of ['sog', 'cog', 'heading', 'nav_stat', 'prediction_method',
      'predicted_latitude', 'predicted_longitude', 'prediction_for_timestamp', 'prediction_made_at']) {
      assert.equal(vessel[key], null, key);
    }
    assert.equal(vessel.vessel_status, 'Unknown');
    assert.equal(vessel.pos_acc, false);
  }
});

test('invalid records and stale or future source times are rejected without losing valid neighbors', async t => {
  const h = harness(t, [feature(), null, {}, feature(0), feature(true), feature(1.5),
    feature(1000000000), feature(230123457, {}, [181, 60]), feature(230123458, {}, [24, false]),
    feature(230123459, {}, [24, 49]), feature(230123460, {}, [31, 60]),
    feature(230123461, { timestampExternal: now - 1_800_001 }),
    feature(230123462, { timestampExternal: now + 60_000 }),
    feature(230123463, { timestampExternal: null }),
    feature(230123464, { timestampExternal: sourceTime / 1000 }),
    feature(230123465, { timestampExternal: 'bad' }),
    { ...feature(230123466), geometry: { type: 'LineString', coordinates: [24, 60] } }]);
  const response = await h.request();
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).map(v => v.vessel_id), [230123456]);
});

test('freshest observation wins duplicates and list limit chooses freshest vessels', async t => {
  const h = harness(t, [feature(230123456, { timestampExternal: now - 300_000 }),
    feature(230123457, { timestampExternal: now - 100_000 }),
    feature(230123456, { timestampExternal: now - 30_000 }, [25, 60])]);
  const response = await h.request('/vessels?limit=1');
  assert.equal(response.status, 200);
  const [vessel] = await response.json();
  assert.equal(vessel.vessel_id, 230123456);
  assert.equal(vessel.current_longitude, 25);
});

test('slow vessels and unsafe displacements have no projection', async t => {
  const h = harness(t, [feature(230123456, { sog: 0.49 }),
    feature(230123457, { sog: 50 }), feature(230123458, {}, [29.99, 60]),
    feature(230123459, { cog: 0 }, [24, 69.99])]);
  const response = await h.request();
  assert.equal(response.status, 200);
  for (const vessel of await response.json()) {
    assert.equal(vessel.prediction_method, null);
    assert.equal(vessel.predicted_latitude, null);
    assert.equal(vessel.predicted_longitude, null);
  }
});

test('MMSI zero never resolves an unrelated vessel and detail misses return 404', async t => {
  const h = harness(t);
  const zero = await h.request('/vessels?mmsi=0');
  assert.equal(zero.status, 200);
  assert.deepEqual(await zero.json(), []);
  assert.equal((await h.request('/vessels/0')).status, 404);
  assert.equal((await h.request('/vessels/999')).status, 404);
  const detail = await h.request('/vessels/230123456');
  assert.equal(detail.status, 200);
  assert.equal((await detail.json()).vessel_id, 230123456);
});

test('time filters interpret naive dates as UTC and apply Python two-hour defaults', async t => {
  const h = harness(t);
  const after = iso(sourceTime + 1000).replace('Z', '');
  const before = iso(sourceTime - 1000);
  for (const query of [`from_time=${after}`, `to_time=${before}`]) {
    const response = await h.request(`/vessels?${query}`);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), []);
  }
  const inside = await h.request(`/vessels?from_time=${before}`);
  assert.equal(inside.status, 200);
  assert.equal((await inside.json()).length, 1);
});

test('bad filters fail before contacting upstream and limits clamp like Python', async t => {
  const h = harness(t);
  for (const query of ['from_time=nope', 'to_time=2026-02-30T12:00:00',
    'from_time=2026-10-14&to_time=2026-10-13', 'format=xml']) {
    const route = query.startsWith('format') ? '/vessels/download' : '/vessels';
    assert.equal((await h.request(`${route}?${query}`)).status, 400, query);
  }
  for (const query of ['mmsi=bad', 'mmsi=1.5', 'limit=bad', 'limit=Infinity']) {
    assert.equal((await h.request(`/vessels?${query}`)).status, 422, query);
  }
  assert.equal(h.calls.length, 0);
  const negativeLimit = await h.request('/vessels?limit=-5');
  assert.equal(negativeLimit.status, 200);
  assert.equal((await negativeLimit.json()).length, 1);
});

test('CSV and JSON exports use the same filters and known AIS fields', async t => {
  const h = harness(t);
  const json = await h.request('/vessels/download?format=json&mmsi=230123456');
  assert.equal(json.status, 200);
  assert.match(json.headers.get('Content-Disposition'), /vessel_230123456_data.json/);
  assert.equal((await json.json())[0].data_source, 'ais');
  const csv = await h.request('/vessels/download?format=csv');
  assert.equal(csv.status, 200);
  assert.match(csv.headers.get('Content-Type'), /text\/csv/);
  const lines = (await csv.text()).trim().split('\r\n');
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^vessel_id,current_latitude,current_longitude,current_timestamp,sog,cog,heading,/);
  assert.match(lines[0], /,prediction_made_at,projection_land_conflict,projection_clear_until_fraction$/);
  assert.match(lines[1], /^230123456,60,24,/);
  assert.match(lines[1], /Unknown,,Finland,ais,dead_reckoning/);
  const empty = await h.request('/vessels/download?format=csv&mmsi=0');
  assert.equal(await empty.text(), 'vessel_id,current_latitude,current_longitude,current_timestamp\r\n');
});

test('all query variants reuse one 30-second snapshot cache', async t => {
  const h = harness(t);
  for (const path of ['/vessels?limit=500', '/vessels?mmsi=0', '/vessels/230123456',
    '/vessels/download?format=csv', '/health']) {
    assert.equal((await h.request(path)).status, 200);
  }
  await Promise.all(h.pending);
  assert.equal(h.calls.length, 1);
  assert.equal(h.entries.size, 1);
  const [key, value] = [...h.entries][0];
  assert.equal(new URL(key).search, '');
  assert.equal(value.headers.get('Cache-Control'), 'public, max-age=30');
  assert.equal(h.pending.length, 1);
});

test('expired cache reloads upstream and near-stale rows cannot survive a cache hit', async t => {
  t.mock.method(Date, 'now', () => now);
  const h = harness(t, [feature(230123456, { timestampExternal: now - 1_790_000 })]);
  assert.equal((await (await h.request()).json()).length, 1);
  t.mock.method(Date, 'now', () => now + 15_000);
  const stale = await h.request();
  assert.equal(stale.status, 200);
  assert.deepEqual(await stale.json(), []);
  assert.equal(h.calls.length, 1);
  t.mock.method(Date, 'now', () => now + 31_000);
  assert.equal((await h.request()).status, 200);
  assert.equal(h.calls.length, 2);
});

test('upstream HTTP failure, bad JSON or schema, and network failure return generic 503', async t => {
  for (const upstream of [() => new Response('private upstream details', { status: 503 }),
    () => new Response('bad json'), () => Response.json({ features: [] }),
    () => Response.json({ type: 'FeatureCollection', features: {} }),
    () => { throw new Error('private exception'); }]) {
    const h = harness(t, [], upstream);
    const response = await h.request();
    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), { detail: 'AIS upstream unavailable' });
    assert.equal(h.entries.size, 0);
  }
});

test('Worker fetch uses supported manual redirect mode and rejects upstream redirects', async t => {
  const h = harness(t, [], (url, options) => {
    if (!['manual', 'follow'].includes(options.redirect)) throw new TypeError('Unsupported Worker redirect mode');
    return Response.json({ type: 'FeatureCollection', features: [feature()] });
  });
  const response = await h.request();
  assert.equal(response.status, 200);
  assert.equal(h.calls[0].options.redirect, 'manual');
  const redirected = harness(t, [], () => new Response(null, {
    status: 302, headers: { Location: 'https://unexpected.example/private' },
  }));
  const blocked = await redirected.request();
  assert.equal(blocked.status, 503);
  assert.deepEqual(await blocked.json(), { detail: 'AIS upstream unavailable' });
  assert.equal(redirected.calls.length, 1);
});

test('upstream bodies over 2 MiB are rejected even without Content-Length', async t => {
  const h = harness(t, [], () => new Response(`{"type":"FeatureCollection","features":[],"padding":"${'x'.repeat(2 * 1024 * 1024)}"}`));
  const response = await h.request();
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { detail: 'AIS upstream unavailable' });
});

test('upstream timeout aborts after eight seconds', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let started;
  const gate = new Promise(resolve => { started = resolve; });
  let signal;
  const h = harness(t, [], (url, options) => {
    signal = options.signal;
    started();
    return new Promise(() => {});
  });
  const request = h.request();
  assert.equal(await Promise.race([gate.then(() => true), request.then(() => false)]), true);
  t.mock.timers.tick(8000);
  const response = await request;
  assert.equal(response.status, 503);
  assert.equal(signal.aborted, true);
});

test('metadata is live, health reports upstream availability, docs serve HTML, and other routes use assets', async t => {
  const h = harness(t);
  const meta = await h.request('/meta');
  assert.equal(meta.status, 200);
  assert.deepEqual(await meta.json(), { mode: 'live', prediction_method: 'dead_reckoning', prediction_horizon_minutes: 30, observation_stale_after_seconds: 300 });
  const docs = await h.request('/docs');
  assert.equal(docs.status, 200);
  assert.match(docs.headers.get('Content-Type'), /text\/html/);
  assert.match(await docs.text(), /Digitraffic/);
  const assets = await h.request('/index.html');
  assert.equal(await assets.text(), 'static page');
  assert.equal(h.calls.length, 0);
  const health = await h.request('/health');
  assert.equal(health.status, 200);
  assert.equal((await health.json()).upstream, 'available');
  const down = harness(t, [], () => new Response('', { status: 503 }));
  const unhealthy = await down.request('/health');
  assert.equal(unhealthy.status, 503);
  assert.equal((await unhealthy.json()).upstream, 'unavailable');
});

test('non-GET API requests reject with 405 without upstream work', async t => {
  const h = harness(t);
  const response = await h.request('/vessels', 'POST');
  assert.equal(response.status, 405);
  assert.equal(response.headers.get('Allow'), 'GET');
  assert.equal(h.calls.length, 0);
});

test('projections across land are flagged with the clear fraction but never dropped', async t => {
  // West of Gotland heading east at 30 kn: the 30-minute straight line ends inside the island.
  const h = harness(t, [feature(230123456, { sog: 30, cog: 90 }, [17.9, 57.6])]);
  const [vessel] = await (await h.request()).json();
  assert.equal(vessel.prediction_method, 'dead_reckoning');
  assert.ok(vessel.predicted_longitude > 18.3);
  assert.equal(vessel.projection_land_conflict, true);
  assert.ok(vessel.projection_clear_until_fraction > 0.4 && vessel.projection_clear_until_fraction < 0.8,
    String(vessel.projection_clear_until_fraction));
});

test('open-water, unresolved-start and unprojected vessels get false or null land flags', async t => {
  const h = harness(t, [feature(230123456, { sog: 12, cog: 90 }, [20.0, 58.5]), // Baltic proper
    feature(230123457, { sog: 8, cog: 90 }, [24.9525, 60.1695]), // Helsinki: start on land => unresolved
    feature(230123458, { sog: 0.1 }, [20.0, 58.5])]); // no projection
  const byId = Object.fromEntries((await (await h.request()).json()).map(v => [v.vessel_id, v]));
  assert.equal(byId[230123456].projection_land_conflict, false);
  assert.equal(byId[230123456].projection_clear_until_fraction, null);
  assert.equal(byId[230123457].prediction_method, 'dead_reckoning');
  assert.equal(byId[230123457].projection_land_conflict, null);
  assert.equal(byId[230123457].projection_clear_until_fraction, null);
  assert.equal(byId[230123458].prediction_method, null);
  assert.equal(byId[230123458].projection_land_conflict, null);
});

test('land mask covers 9..31E 53.5..66N and treats outside points as water', () => {
  assert.deepEqual(maskInfo.bbox, { west: 9, south: 53.5, east: 31, north: 66 });
  assert.equal(isLand(57.5, 18.5), true); // Gotland interior
  assert.equal(isLand(58.5, 20.0), false); // Baltic proper
  for (const [lat, lon] of [[50, 20], [70, 20], [60, 8], [60, 32], [53.49, 20], [NaN, 20]]) {
    assert.equal(isLand(lat, lon), false, `${lat},${lon}`);
  }
  assert.equal(pathHitsLand(50, 10, 51, 12), false); // entirely outside mask
  assert.equal(pathHitsLand(57.5, 18.5, 57.5, 18.6), null); // start on land: unresolved
  assert.equal(pathHitsLand(57.6, 17.9, 57.6, 18.4), true);
  assert.equal(clearUntilFraction(58.5, 20, 58.5, 20.2), null);
});
