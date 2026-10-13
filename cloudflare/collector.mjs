// Archives raw Digitraffic objects into D1 table archive_objects (migrations/0001_archive_objects.sql;
// see docs/evaluation.md): one gzipped NDJSON AIS snapshot per minute, one metadata JSON per day.
// Works from raw features, not normalize(): keeps rot and sentinel values (sog 102.3, cog 360, heading 511).
const num = value => (typeof value === 'number' && Number.isFinite(value) ? value : null);

function record(feature, fetchedAt) {
  const p = feature?.properties;
  const geometry = feature?.geometry;
  const [lon, lat] = geometry?.type === 'Point' && Array.isArray(geometry.coordinates) ? geometry.coordinates : [];
  const mmsi = num(p?.mmsi);
  const latitude = num(lat);
  const longitude = num(lon);
  if (!Number.isInteger(mmsi) || mmsi <= 0 || mmsi > 999999999
      || latitude === null || latitude < -90 || latitude > 90
      || longitude === null || longitude < -180 || longitude > 180) return null;
  const ts = Number.isSafeInteger(p?.timestampExternal) ? p.timestampExternal : null;
  return {
    mmsi, lat: latitude, lon: longitude, timestampExternal: ts,
    age_s: ts === null ? null : Math.round((fetchedAt - ts) / 1000),
    sog: num(p?.sog), cog: num(p?.cog), heading: num(p?.heading), rot: num(p?.rot),
    navStat: num(p?.navStat), posAcc: p?.posAcc ?? null, raim: p?.raim ?? null,
  };
}

// D1 rows are limited to 2 MB and the downloader reads hex(body), which doubles the size on the wire;
// scripts/archive/download_d1.py rejects bodies over the same cap.
export const MAX_BODY_BYTES = 900_000;
// Pause when the oldest AIS row is older than this: ~43 MB/day * 8 days ~ 345 MB of D1 Free's 500 MB.
// Age, not database size: SQLite may not shrink after DELETE, so a size-based pause might never lift.
export const MAX_RETENTION_DAYS = 8;

const text = value => (value == null ? null : String(value));

const stamp = now => new Date(now).toISOString();

// ais/YYYY/MM/DD/HH/mm.ndjson.gz, UTC: one object per minute, so a retry in the same minute is a no-op.
export function archiveKey(now) {
  const t = stamp(now);
  return `ais/${t.slice(0, 4)}/${t.slice(5, 7)}/${t.slice(8, 10)}/${t.slice(11, 13)}/${t.slice(14, 16)}.ndjson.gz`;
}

// meta/YYYY/MM/DD.json.gz, UTC: one object per day.
export function metaKey(now) {
  const t = stamp(now);
  return `meta/${t.slice(0, 4)}/${t.slice(5, 7)}/${t.slice(8, 10)}.json.gz`;
}

async function gzip(text) {
  return new Response(new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
}

function setup(env, now, loader, what) {
  if (!env?.AIS_ARCHIVE_DB) throw new Error('AIS_ARCHIVE_DB binding missing');
  if (!Number.isFinite(now)) throw new Error('Invalid scheduled timestamp');
  if (typeof loader !== 'function') throw new Error(`${what} loader missing`);
}

// One indexed row: the oldest AIS key. Pauses until the owner has downloaded and deleted old days.
async function assertRetention(env, now) {
  const row = await env.AIS_ARCHIVE_DB.prepare(
    "SELECT key FROM archive_objects WHERE key >= 'ais/' AND key < 'ais0' ORDER BY key LIMIT 1",
  ).first();
  const [, y, mo, d, h, mi] = /^ais\/(\d{4})\/(\d{2})\/(\d{2})\/(\d{2})\/(\d{2})\.ndjson\.gz$/.exec(row?.key ?? '') ?? [];
  const oldest = Date.UTC(y, mo - 1, d, h, mi);
  if (now - oldest > MAX_RETENTION_DAYS * 86_400_000) {
    throw new Error('archive paused: retention exceeded, download and clean up');
  }
}

// First write per key wins: ON CONFLICT DO NOTHING makes a retried minute or day a harmless no-op.
async function store(env, row, body) {
  if (body.byteLength > MAX_BODY_BYTES) throw new Error(`Archive body too large: ${body.byteLength} bytes`);
  await env.AIS_ARCHIVE_DB.prepare(
    'INSERT INTO archive_objects(key, kind, scheduled_at, fetched_at, data_updated_at, count, body) '
    + 'VALUES(?, ?, ?, ?, ?, ?, ?) ON CONFLICT(key) DO NOTHING',
  ).bind(row.key, row.kind, row.scheduled_at, row.fetched_at, row.data_updated_at, row.count, body).run();
}

export async function collectSnapshot(env, now, snapshotLoader) {
  try {
    setup(env, now, snapshotLoader, 'Snapshot');
    await assertRetention(env, now);
    const snap = await snapshotLoader();
    if (typeof snap?.source !== 'string' || !snap.source) throw new Error('Snapshot source missing');
    const rows = snap.features.map(feature => record(feature, snap.fetched_at)).filter(Boolean);
    if (!rows.length) throw new Error('Empty snapshot');
    const header = {
      schema: 1, fetched_at: stamp(snap.fetched_at), source: snap.source,
      count: rows.length, data_updated_at: text(snap.updated_at),
    };
    const body = await gzip([header, ...rows].map(line => JSON.stringify(line)).join('\n') + '\n');
    const key = archiveKey(now);
    await store(env, {
      key, kind: 'ais', scheduled_at: now, fetched_at: snap.fetched_at,
      data_updated_at: header.data_updated_at, count: rows.length,
    }, body);
    return { ok: true, key, count: rows.length, bytes: body.byteLength };
  } catch (error) {
    console.error('collectSnapshot failed', error);
    throw error;
  }
}

// Daily vessel metadata (name, callSign, imo, shipType, destination, ...). The feed has no lat/lon,
// so only the MMSI is validated; vessels are archived as received.
export async function collectMetadata(env, now, loader) {
  try {
    setup(env, now, loader, 'Metadata');
    await assertRetention(env, now);
    const snap = await loader();
    if (typeof snap?.source !== 'string' || !snap.source) throw new Error('Metadata source missing');
    const vessels = snap.vessels.filter(v => Number.isInteger(v?.mmsi) && v.mmsi > 0 && v.mmsi <= 999999999);
    if (!vessels.length) throw new Error('Empty metadata');
    const body = await gzip(JSON.stringify({
      schema: 1, source: snap.source, fetched_at: stamp(snap.fetched_at),
      data_updated_at: text(snap.updated_at), count: vessels.length, vessels,
    }));
    const key = metaKey(now);
    await store(env, {
      key, kind: 'meta', scheduled_at: now, fetched_at: snap.fetched_at,
      data_updated_at: text(snap.updated_at), count: vessels.length,
    }, body);
    return { ok: true, key, count: vessels.length, bytes: body.byteLength };
  } catch (error) {
    console.error('collectMetadata failed', error);
    throw error;
  }
}
