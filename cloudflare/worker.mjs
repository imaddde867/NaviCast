import countries from './countries.json' with { type: 'json' };
import { scanPath } from './landmask.mjs';
import { collectMetadata, collectSnapshot } from './collector.mjs';

const UPSTREAM = 'https://meri.digitraffic.fi/api/ais/v1/locations';
const VESSELS_UPSTREAM = 'https://meri.digitraffic.fi/api/ais/v1/vessels';
// Must match triggers.crons in wrangler.jsonc (tests/collector.test.mjs checks this).
export const SNAPSHOT_CRON = '* * * * *';
export const METADATA_CRON = '10 0 * * *';
const HEALTH_MAX_AGE_MS = 5 * 60 * 1000;
const HEALTH_MAX_DATA_AGE_MS = 10 * 60 * 1000;
const HORIZON_MS = 30 * 60 * 1000;
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const NAV_STATUS = [
  'Under way using engine', 'At anchor', 'Not under command', 'Restricted maneuverability',
  'Constrained by draft', 'Moored', 'Aground', 'Engaged in fishing', 'Under way sailing',
  'Reserved', 'Reserved', 'Reserved', 'Reserved', 'Reserved', 'AIS-SART active', 'Not defined',
];

function number(value) {
  if (!['number', 'string'].includes(typeof value)) return null;
  if (typeof value === 'string' && !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(value.trim())) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function motion(value, maximum) {
  const parsed = number(value);
  return parsed !== null && parsed >= 0 && parsed < maximum ? parsed : null;
}

function inRegion(lat, lon) {
  return lat !== null && lon !== null && lat >= 50 && lat <= 70 && lon >= 10 && lon <= 30;
}

function normalize(features, fetchedAt) {
  const vessels = new Map();
  for (const feature of features) {
    const properties = feature?.properties;
    const geometry = feature?.geometry;
    if (!properties || geometry?.type !== 'Point' || !Array.isArray(geometry.coordinates)) continue;
    const id = number(properties.mmsi);
    const [lon, lat] = geometry.coordinates.map(number);
    const timestamp = number(properties.timestampExternal);
    if (!Number.isInteger(id) || id <= 0 || id > 999999999 || !inRegion(lat, lon)
        || timestamp === null || timestamp <= fetchedAt - HORIZON_MS || timestamp > fetchedAt) continue;
    const sourceTime = new Date(timestamp).toISOString();
    if (vessels.has(id) && vessels.get(id).current_timestamp >= sourceTime) continue;
    const sog = motion(properties.sog, 102.3);
    const cog = motion(properties.cog, 360);
    const navValue = motion(properties.navStat, 16);
    const navStat = Number.isInteger(navValue) ? navValue : null;
    const vessel = {
      vessel_id: id,
      current_latitude: lat,
      current_longitude: lon,
      current_timestamp: sourceTime,
      sog, cog, heading: motion(properties.heading, 360),
      pos_acc: properties.posAcc === true,
      nav_stat: navStat,
      vessel_status: NAV_STATUS[navStat] ?? 'Unknown',
      vessel_type: 'Unknown',
      vessel_type_code: null,
      country: countries[String(id).slice(0, 3)] ?? null,
      data_source: 'ais',
      prediction_method: null,
      predicted_latitude: null,
      predicted_longitude: null,
      prediction_for_timestamp: null,
      prediction_made_at: null,
      projection_land_conflict: null,
      projection_clear_until_fraction: null,
    };
    if (sog !== null && sog >= 0.5 && cog !== null) {
      const distance = sog * 0.51444 * 1800;
      const deltaLat = distance * Math.cos(cog * Math.PI / 180) / 111111;
      const deltaLon = distance * Math.sin(cog * Math.PI / 180) / (111111 * Math.cos(lat * Math.PI / 180));
      if (Math.abs(deltaLat) <= 0.5 && Math.abs(deltaLon) <= 0.5 && inRegion(lat + deltaLat, lon + deltaLon)) {
        const { conflict, clear } = scanPath(lat, lon, lat + deltaLat, lon + deltaLon);
        Object.assign(vessel, {
          projection_land_conflict: conflict,
          projection_clear_until_fraction: clear === null ? null : Math.round(clear * 1000) / 1000,
          prediction_method: 'dead_reckoning',
          predicted_latitude: lat + deltaLat,
          predicted_longitude: lon + deltaLon,
          prediction_for_timestamp: new Date(timestamp + HORIZON_MS).toISOString(),
          prediction_made_at: new Date(fetchedAt).toISOString(),
        });
      }
    }
    vessels.set(id, vessel);
  }
  return [...vessels.values()].sort((a, b) => b.current_timestamp.localeCompare(a.current_timestamp));
}

// Fetches one upstream JSON document with the shared 8 s timeout, redirect refusal and 2 MiB cap.
async function fetchJson(upstream) {
  const controller = new AbortController();
  let reader;
  let timer;
  const timeout = new Promise((resolve, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reader?.cancel().catch(() => {});
      reject(new Error('Upstream timeout'));
    }, 8000);
  });
  try {
    return await Promise.race([timeout, (async () => {
      const response = await fetch(upstream, {
        headers: { 'Accept-Encoding': 'gzip', 'Digitraffic-User': 'NaviCast/imadlab.com' },
        signal: controller.signal,
        redirect: 'manual',
      });
      if (!response.ok || Number(response.headers.get('Content-Length')) > MAX_BODY_BYTES || !response.body) {
        await response.body?.cancel();
        throw new Error('Invalid upstream response');
      }
      reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8', { fatal: true });
      const chunks = [];
      let size = 0;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_BODY_BYTES) {
          await reader.cancel();
          throw new Error('Upstream body too large');
        }
        chunks.push(decoder.decode(value, { stream: true }));
      }
      chunks.push(decoder.decode());
      return { payload: JSON.parse(chunks.join('')), fetched_at: Date.now() };
    })()]);
  } finally {
    clearTimeout(timer);
  }
}

export async function loadRawSnapshot() {
  const { payload, fetched_at } = await fetchJson(UPSTREAM);
  if (payload?.type !== 'FeatureCollection' || !Array.isArray(payload.features)) {
    throw new Error('Invalid upstream schema');
  }
  return { fetched_at, source: UPSTREAM, updated_at: payload.dataUpdatedTime ?? null, features: payload.features };
}

export async function loadVesselMetadata() {
  const { payload, fetched_at } = await fetchJson(VESSELS_UPSTREAM);
  if (!Array.isArray(payload)) throw new Error('Invalid upstream schema');
  return { fetched_at, source: VESSELS_UPSTREAM, updated_at: null, vessels: payload };
}

async function loadSnapshot() {
  const raw = await loadRawSnapshot();
  return { fetched_at: raw.fetched_at, vessels: normalize(raw.features, raw.fetched_at) };
}

async function snapshot(url, ctx) {
  const key = new Request(new URL('/__navicast_ais_snapshot_v2', url.origin));
  const cached = await caches.default.match(key);
  if (cached) {
    const result = await cached.json();
    if (Date.now() - result.fetched_at < 30_000) return result;
  }
  const result = await loadSnapshot();
  const saved = caches.default.put(key, Response.json(result, { headers: { 'Cache-Control': 'public, max-age=30' } }));
  ctx.waitUntil(saved);
  await saved;
  return result;
}

function json(value, status = 200, headers = {}) {
  return Response.json(value, { status, headers: { 'Cache-Control': 'no-store', ...headers } });
}

function integer(value, name) {
  if (!/^[+-]?\d+$/.test(value.trim()) || !Number.isSafeInteger(Number(value))) {
    throw { status: 422, detail: `Invalid ${name}: expected an integer` };
  }
  return Number(value);
}

function timestamp(value, name) {
  if (value === null) return null;
  const parts = /^(\d{4})-(\d{2})-(\d{2})(?:[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?(Z|[+-]\d{2}:\d{2})?)?$/.exec(value);
  if (parts) {
    const [, year, month, day, hour, minute, second, , zone] = parts;
    const maxDay = new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate();
    const parsed = Date.parse(hour === undefined ? value : value.replace(' ', 'T') + (zone ? '' : 'Z'));
    if (Number(year) > 0 && Number(month) >= 1 && Number(month) <= 12 && Number(day) >= 1
        && Number(day) <= maxDay && Number(hour ?? 0) < 24 && Number(minute ?? 0) < 60
        && Number(second ?? 0) < 60 && Number.isFinite(parsed)) return parsed;
  }
  throw { status: 400, detail: `Invalid ${name} format. Use ISO format (YYYY-MM-DDTHH:MM:SS)` };
}

function filters(params) {
  const mmsi = params.has('mmsi') ? integer(params.get('mmsi'), 'mmsi') : null;
  let start = timestamp(params.get('from_time'), 'from_time');
  let end = timestamp(params.get('to_time'), 'to_time');
  if (start === null && end !== null) start = end - 2 * 60 * 60 * 1000;
  if (end === null && start !== null) end = start + 2 * 60 * 60 * 1000;
  if (start !== null && end !== null && start > end) throw { status: 400, detail: 'from_time must be before to_time' };
  return { mmsi, start, end };
}

function csv(vessels) {
  const fields = vessels.length ? Object.keys(vessels[0]) : ['vessel_id', 'current_latitude', 'current_longitude', 'current_timestamp'];
  const cell = value => {
    const text = value == null ? '' : typeof value === 'boolean' ? (value ? 'True' : 'False') : String(value);
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  return [fields.join(','), ...vessels.map(vessel => fields.map(field => cell(vessel[field])).join(','))].join('\r\n') + '\r\n';
}

// Reads exactly one row through the primary-key index (newest 'ais/' key), never MAX() over the table,
// so a health poll costs a couple of rows read against D1's 5M/day free quota. Exposes only ok/age_s.
// 503 when collection stopped (fetched_at old) or the upstream froze (data_updated_at old while the
// collector keeps fetching). A null or unparseable data_updated_at is not a failure by itself.
async function health(env) {
  try {
    const row = await env.AIS_ARCHIVE_DB.prepare(
      "SELECT fetched_at, data_updated_at FROM archive_objects WHERE key >= 'ais/' AND key < 'ais0' ORDER BY key DESC LIMIT 1",
    ).first();
    if (!Number.isFinite(row?.fetched_at)) return json({ ok: false }, 503);
    const now = Date.now();
    const age = now - row.fetched_at;
    const dataTime = row.data_updated_at == null ? NaN : Date.parse(row.data_updated_at);
    const ok = age <= HEALTH_MAX_AGE_MS && !(now - dataTime > HEALTH_MAX_DATA_AGE_MS);
    return json({ ok, age_s: Math.round(age / 1000) }, ok ? 200 : 503);
  } catch (error) {
    console.error('health check failed', error);
    return json({ ok: false }, 503);
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method !== 'GET') return json({ detail: 'Method not allowed' }, 405, { Allow: 'GET' });
    if (url.pathname === '/meta') return json({ mode: 'live', prediction_method: 'dead_reckoning', prediction_horizon_minutes: 30, observation_stale_after_seconds: 300 });
    if (url.pathname === '/docs') return new Response(`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>NaviCast API</title><main><h1>NaviCast live API</h1><p>Digitraffic AIS observations in the Baltic region, cached for up to 30 seconds. Only observations from the last 30 minutes are returned. Constant speed and course projections target 30 minutes after the source observation; unavailable motion produces no projection. <code>projection_land_conflict</code> is true when the straight-line projection crosses land in an OpenStreetMap coastline mask (<code>projection_clear_until_fraction</code> is then the fraction of the path before the coast), false when no land was found along it inside the mask area (9–31°E, 53.5–66°N), and null when it cannot be resolved: no projection, a start position on mapped land, or a path that leaves the mask area before reaching land (positions outside the mask are unknown, not assumed to be water). The mask is approximate: the path is sampled every 100 m, inland lakes count as land, and islets smaller than a 0.001° grid cell can be absent, so a clear flag is not a guarantee. The projection itself is never altered and the flags are not for navigation.</p><ul><li><a href="/vessels?limit=500">GET /vessels</a>: optional mmsi, from_time, to_time, limit (1–1000, default 100). ISO dates use UTC unless an offset is supplied. Time filters select the current snapshot, with a two-hour default range.</li><li>GET /vessels/{MMSI}: one vessel, or 404.</li><li><a href="/vessels/download?format=csv">GET /vessels/download</a>: format=json|csv, with the same MMSI and time filters, up to 10000 rows.</li><li><a href="/meta">GET /meta</a>: mode and prediction horizon.</li><li><a href="/health">GET /health</a>: archive freshness, 200 when the newest archived AIS snapshot is under five minutes old, otherwise 503.</li></ul><p>The edge API uses no historical database or trained model. Ship type is unknown in the location feed. Upstream failures return 503.</p><p>Source: <a href="https://www.digitraffic.fi/en/marine-traffic/">Fintraffic / digitraffic.fi</a>, license <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. Observations are filtered and normalized; constant-course estimates are added. Data and estimates are not for navigation. Coastline flags: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, ODbL.</p></main></html>`, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    const detailMatch = /^\/vessels\/([^/]+)$/.exec(url.pathname);
    const download = url.pathname === '/vessels/download';
    if (url.pathname === '/health') return health(env);
    if (url.pathname !== '/vessels' && !detailMatch) return env.ASSETS.fetch(request);
    try {
      const query = download || !detailMatch ? filters(url.searchParams)
        : { mmsi: integer(detailMatch[1], 'vessel_id'), start: null, end: null };
      const format = url.searchParams.get('format') ?? 'json';
      if (download && !['json', 'csv'].includes(format)) throw { status: 400, detail: "Format must be 'json' or 'csv'" };
      const limit = download ? 10000 : detailMatch ? 1
        : Math.min(1000, Math.max(1, url.searchParams.has('limit') ? integer(url.searchParams.get('limit'), 'limit') : 100));
      const result = await snapshot(url, ctx);
      const now = Date.now();
      const vessels = result.vessels.filter(vessel => {
        const time = Date.parse(vessel.current_timestamp);
        return time > now - HORIZON_MS && time <= now && (query.mmsi === null || vessel.vessel_id === query.mmsi)
          && (query.start === null || time >= query.start) && (query.end === null || time <= query.end);
      }).slice(0, limit);
      if (download) {
        const filename = query.mmsi === null ? `vessel_data.${format}` : `vessel_${query.mmsi}_data.${format}`;
        const headers = { 'Content-Disposition': `attachment; filename=${filename}` };
        return format === 'json' ? json(vessels, 200, headers) : new Response(csv(vessels), {
          headers: { ...headers, 'Content-Type': 'text/csv; charset=utf-8', 'Cache-Control': 'no-store' },
        });
      }
      if (detailMatch) return vessels.length ? json(vessels[0]) : json({ detail: 'Vessel not found' }, 404);
      return json(vessels);
    } catch (error) {
      if (error.status === 400 || error.status === 422) return json({ detail: error.detail }, error.status);
      return json({ detail: 'AIS upstream unavailable' }, 503);
    }
  },
  // Awaited, not ctx.waitUntil: a rejection must fail the cron run so it shows in the cron status.
  async scheduled(event, env) {
    if (event.cron === SNAPSHOT_CRON) return collectSnapshot(env, event.scheduledTime, loadRawSnapshot);
    if (event.cron === METADATA_CRON) return collectMetadata(env, event.scheduledTime, loadVesselMetadata);
    throw new Error('Unknown cron');
  },
};
