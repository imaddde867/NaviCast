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
  const ts = num(p?.timestampExternal);
  return {
    mmsi, lat: latitude, lon: longitude, timestampExternal: ts,
    age_s: ts === null ? null : Math.round((fetchedAt - ts) / 1000),
    sog: num(p?.sog), cog: num(p?.cog), heading: num(p?.heading), rot: num(p?.rot),
    navStat: num(p?.navStat), posAcc: p?.posAcc ?? null, raim: p?.raim ?? null,
  };
}

// D1 rows are limited to 2 MB; scripts/archive/download_d1.py rejects bodies over the same cap.
export const MAX_BODY_BYTES = 1_900_000;
// Pause writes at this database size so the owner can download, verify and delete (docs/hosting.md).
export const PAUSE_AT_BYTES = 350_000_000;

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

// Reads the D1 size from meta.size_after of a trivial query. The docs list size_after in the result
// meta object and show it on a SELECT; that read queries return it is taken from that example and was
// not tested against a live database. Fails closed if the field is absent rather than silently unguarded.
async function assertCapacity(env) {
  const { meta } = await env.AIS_ARCHIVE_DB.prepare('SELECT 1').run();
  if (!Number.isFinite(meta?.size_after)) throw new Error('archive paused: D1 size unavailable');
  if (meta.size_after >= PAUSE_AT_BYTES) throw new Error('archive paused: storage threshold');
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
    await assertCapacity(env);
    const snap = await snapshotLoader();
    if (typeof snap?.source !== 'string' || !snap.source) throw new Error('Snapshot source missing');
    const rows = snap.features.map(feature => record(feature, snap.fetched_at)).filter(Boolean);
    if (!rows.length) throw new Error('Empty snapshot');
    const header = {
      schema: 1, fetched_at: stamp(snap.fetched_at), source: snap.source,
      count: rows.length, data_updated_at: snap.updated_at ?? null,
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
    await assertCapacity(env);
    const snap = await loader();
    if (typeof snap?.source !== 'string' || !snap.source) throw new Error('Metadata source missing');
    const vessels = snap.vessels.filter(v => Number.isInteger(v?.mmsi) && v.mmsi > 0 && v.mmsi <= 999999999);
    if (!vessels.length) throw new Error('Empty metadata');
    const body = await gzip(JSON.stringify({
      schema: 1, source: snap.source, fetched_at: stamp(snap.fetched_at),
      data_updated_at: snap.updated_at ?? null, count: vessels.length, vessels,
    }));
    const key = metaKey(now);
    await store(env, {
      key, kind: 'meta', scheduled_at: now, fetched_at: snap.fetched_at,
      data_updated_at: snap.updated_at ?? null, count: vessels.length,
    }, body);
    return { ok: true, key, count: vessels.length, bytes: body.byteLength };
  } catch (error) {
    console.error('collectMetadata failed', error);
    throw error;
  }
}
