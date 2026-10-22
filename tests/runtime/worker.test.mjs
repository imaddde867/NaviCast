import { env, exports } from 'cloudflare:workers';
import { applyD1Migrations, createScheduledController, reset } from 'cloudflare:test';
import { beforeEach, afterEach, expect, test, vi } from 'vitest';
import { archiveKey, collectSnapshot } from '../../cloudflare/collector.mjs';
import worker, { SNAPSHOT_CRON, METADATA_CRON } from '../../cloudflare/worker.mjs';

const now = Date.UTC(2026, 9, 14, 12);
const feature = {
  type: 'Feature', geometry: { type: 'Point', coordinates: [20, 57] },
  properties: { mmsi: 230000001, timestampExternal: now - 60_000,
    sog: 8, cog: 0, heading: 511, rot: -128 },
};
const upstream = { type: 'FeatureCollection', dataUpdatedTime: new Date(now).toISOString(), features: [feature] };
const request = path => exports.default.fetch(`https://navicast.test${path}`);
const rows = async () => (await env.AIS_ARCHIVE_DB.prepare('SELECT * FROM archive_objects ORDER BY key').all()).results;
const schedule = cron => worker.scheduled(createScheduledController({ cron, scheduledTime: now }), env);
const unzip = body => new Response(new Blob([new Uint8Array(body)]).stream()
  .pipeThrough(new DecompressionStream('gzip'))).text();

beforeEach(async () => {
  await applyD1Migrations(env.AIS_ARCHIVE_DB, env.TEST_MIGRATIONS);
  vi.spyOn(Date, 'now').mockReturnValue(now);
  // Every outbound request is replaced, including unexpected destinations.
  vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('Unexpected outbound request'); }));
});
afterEach(async () => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  await reset();
});

test('entrypoint metadata and invalid queries need no upstream', async () => {
  expect(await (await request('/meta')).json()).toEqual({ mode: 'live', prediction_method: 'dead_reckoning',
    prediction_horizon_minutes: 30, observation_stale_after_seconds: 300 });
  for (const [path, status] of [['/vessels?limit=bad', 422], ['/vessels?from_time=nope', 400],
    ['/vessels/download?format=xml', 400]]) {
    expect((await request(path)).status).toBe(status);
  }
  expect(fetch).not.toHaveBeenCalled();
});

test('list, detail and exports agree through real entrypoint and runtime cache', async () => {
  fetch.mockImplementation(async () => Response.json(upstream));
  const fleet = await (await request('/vessels')).json();
  expect(fleet).toHaveLength(1);
  expect(fleet[0]).toMatchObject({ vessel_id: 230000001, heading: null, prediction_method: 'dead_reckoning' });
  expect(await (await request('/vessels/230000001')).json()).toEqual(fleet[0]);
  expect(await (await request('/vessels/download')).json()).toEqual(fleet);
  const csv = await request('/vessels/download?format=csv');
  expect(csv.headers.get('Content-Type')).toContain('text/csv');
  expect(await csv.text()).toContain('230000001,57,20,');
  expect((await request('/vessels/230000002')).status).toBe(404);
  expect(fetch).toHaveBeenCalledTimes(1);
});

test.each(['http', 'schema', 'network'])('upstream %s failure returns generic 503', async kind => {
  fetch.mockImplementation(async () => {
    if (kind === 'network') throw new Error('private upstream detail');
    return kind === 'http' ? new Response('private', { status: 500 }) : Response.json({ features: [] });
  });
  const response = await request('/vessels');
  expect(response.status).toBe(503);
  expect(await response.json()).toEqual({ detail: 'AIS upstream unavailable' });
});

test('live health shares the runtime cache and preserves historical D1 rows', async () => {
  const old = now - 3 * 86_400_000;
  await env.AIS_ARCHIVE_DB.prepare('INSERT INTO archive_objects VALUES (?, ?, ?, ?, ?, ?, ?)')
    .bind(archiveKey(old), 'ais', old, old, null, 1, new Uint8Array([1]).buffer).run();
  const before = await rows();
  fetch.mockImplementation(async () => Response.json(upstream));
  const health = await request('/health');
  expect(health.status).toBe(200);
  expect(health.headers.get('Cache-Control')).toBe('no-store');
  expect(await health.json()).toEqual({ ok: true, age_s: 0 });
  expect((await request('/vessels')).status).toBe(200);
  expect((await request('/health/archive')).status).toBe(503);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(await rows()).toEqual(before);
  await env.AIS_ARCHIVE_DB.exec('DROP TABLE archive_objects');
  expect((await request('/health')).status).toBe(200);
});

test('live health returns generic 503 when the upstream is unavailable', async () => {
  const health = await request('/health');
  expect(health.status).toBe(503);
  expect(health.headers.get('Cache-Control')).toBe('no-store');
  expect(await health.json()).toEqual({ ok: false });
});

test('minute cron writes real migrated D1, gzip, timestamps and raw sentinels once', async () => {
  const raw = structuredClone(upstream);
  raw.features[0].properties.sog = 102.3;
  raw.features[0].properties.cog = 360;
  fetch.mockImplementation(async () => Response.json(raw));
  await schedule(SNAPSHOT_CRON);
  fetch.mockImplementation(async () => Response.json(upstream));
  await schedule(SNAPSHOT_CRON);
  const stored = await rows();
  expect(stored).toHaveLength(1);
  const [row] = stored;
  expect(row).toMatchObject({ key: 'ais/2026/10/14/12/00.ndjson.gz', kind: 'ais',
    scheduled_at: now, fetched_at: now, data_updated_at: '2026-10-14T12:00:00.000Z', count: 1 });
  const [header, observation] = (await unzip(row.body)).trim().split('\n').map(JSON.parse);
  expect(header).toEqual({ schema: 1, fetched_at: '2026-10-14T12:00:00.000Z',
    source: 'https://meri.digitraffic.fi/api/ais/v1/locations', count: 1, data_updated_at: upstream.dataUpdatedTime });
  expect(observation).toMatchObject({ mmsi: 230000001, sog: 102.3, cog: 360, heading: 511, rot: -128, age_s: 60 });
  expect((await request('/health/archive')).status).toBe(200);
});

test('daily cron stores metadata without coordinates', async () => {
  const vessels = [{ mmsi: 230000001, name: 'SYNTHETIC TEST' }];
  fetch.mockImplementation(async () => Response.json(vessels));
  await schedule(METADATA_CRON);
  const [row] = await rows();
  expect(row.key).toBe('meta/2026/10/14.json.gz');
  expect(JSON.parse(await unzip(row.body)).vessels).toEqual(vessels);
  expect((await request('/health/archive')).status).toBe(503);
});

test('retention boundary blocks cron before upstream and leaves database unchanged', async () => {
  const old = now - 9 * 86_400_000;
  await env.AIS_ARCHIVE_DB.prepare('INSERT INTO archive_objects VALUES (?, ?, ?, ?, ?, ?, ?)')
    .bind(archiveKey(old), 'ais', old, old, null, 1, new Uint8Array([1]).buffer).run();
  await expect(schedule(SNAPSHOT_CRON)).rejects.toThrow('retention exceeded');
  expect(fetch).not.toHaveBeenCalled();
  expect(await rows()).toHaveLength(1);
  expect((await request('/health/archive')).status).toBe(503);
});

test('cron and collector database failures propagate; health fails closed', async () => {
  await env.AIS_ARCHIVE_DB.exec('DROP TABLE archive_objects');
  await expect(schedule(SNAPSHOT_CRON)).rejects.toThrow();
  await expect(collectSnapshot(env, now, async () => upstream)).rejects.toThrow();
  const health = await request('/health/archive');
  expect(health.status).toBe(503);
  expect(await health.json()).toEqual({ ok: false });
  expect(fetch).not.toHaveBeenCalled();
});

test('a real D1 write rejection fails the cron instead of reporting success', async () => {
  await env.AIS_ARCHIVE_DB.exec("CREATE TRIGGER reject_archive BEFORE INSERT ON archive_objects BEGIN SELECT RAISE(ABORT, 'write rejected'); END;");
  fetch.mockImplementation(async () => Response.json(upstream));
  await expect(schedule(SNAPSHOT_CRON)).rejects.toThrow('write rejected');
  expect(await rows()).toEqual([]);
});

test('failed upstream cron writes nothing and unknown cron rejects', async () => {
  await expect(schedule(SNAPSHOT_CRON)).rejects.toThrow();
  expect(await rows()).toEqual([]);
  await expect(schedule('unknown')).rejects.toThrow('Unknown cron');
});

test('real migration enforces kind and null constraints', async () => {
  await expect(env.AIS_ARCHIVE_DB.prepare('INSERT INTO archive_objects VALUES (?, ?, ?, ?, ?, ?, ?)')
    .bind('invalid', 'invalid', now, now, null, 0, new Uint8Array([1]).buffer).run()).rejects.toThrow();
  await expect(env.AIS_ARCHIVE_DB.prepare('INSERT INTO archive_objects (key, kind) VALUES (?, ?)')
    .bind('incomplete', 'ais').run()).rejects.toThrow();
  expect(await rows()).toEqual([]);
});
