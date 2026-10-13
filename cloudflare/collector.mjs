// Archives one raw AIS snapshot per invocation to R2 as gzipped NDJSON (see docs/evaluation.md).
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

// ais/YYYY/MM/DD/HH/mm.ndjson.gz, UTC: one object per minute, so a retry in the same minute overwrites.
export function archiveKey(now) {
  const t = new Date(now).toISOString();
  return `ais/${t.slice(0, 4)}/${t.slice(5, 7)}/${t.slice(8, 10)}/${t.slice(11, 13)}/${t.slice(14, 16)}.ndjson.gz`;
}

async function gzip(text) {
  return new Response(new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
}

export async function collectSnapshot(env, now, snapshotLoader) {
  try {
    if (!env?.AIS_ARCHIVE) throw new Error('AIS_ARCHIVE binding missing');
    if (!Number.isFinite(now)) throw new Error('Invalid scheduled timestamp');
    if (typeof snapshotLoader !== 'function') throw new Error('Snapshot loader missing');
    const snap = await snapshotLoader();
    if (typeof snap?.source !== 'string' || !snap.source) throw new Error('Snapshot source missing');
    const rows = snap.features.map(feature => record(feature, snap.fetched_at)).filter(Boolean);
    if (!rows.length) throw new Error('Empty snapshot');
    const header = {
      schema: 1, fetched_at: new Date(snap.fetched_at).toISOString(), source: snap.source,
      count: rows.length, data_updated_at: snap.updated_at ?? null,
    };
    const body = await gzip([header, ...rows].map(line => JSON.stringify(line)).join('\n') + '\n');
    const key = archiveKey(now);
    await env.AIS_ARCHIVE.put(key, body, { httpMetadata: { contentType: 'application/gzip' } });
    return { ok: true, key, count: rows.length, bytes: body.byteLength };
  } catch (error) {
    console.error('collectSnapshot failed', error);
    throw error;
  }
}
