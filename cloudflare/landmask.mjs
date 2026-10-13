// Land/water lookup over cloudflare/land_mask.json (built by scripts/build_land_mask.py).
// Data © OpenStreetMap contributors, ODbL. Points outside the mask bbox are unknown (null), never assumed to be water.
import mask from './land_mask.json' with { type: 'json' };

const { west, north } = mask.bbox;
const { cell_deg: CELL, cols: COLS, rows: ROWS } = mask;
let rowStart;
let bounds; // flat Int32Array of cumulative run boundaries; land cells lie between odd/even pairs

function load() {
  const bytes = Uint8Array.from(atob(mask.data), c => c.charCodeAt(0));
  const out = [];
  rowStart = new Int32Array(ROWS + 1);
  let p = 0;
  const varint = () => {
    let v = 0;
    for (let shift = 0; ; shift += 7) {
      const b = bytes[p++];
      v += (b & 0x7f) * 2 ** shift;
      if (b < 0x80) return v;
    }
  };
  for (let r = 0; r < ROWS; r++) {
    rowStart[r] = out.length;
    let n = varint();
    let at = 0;
    while (n-- > 0) out.push(at += varint());
  }
  rowStart[ROWS] = out.length;
  bounds = Int32Array.from(out);
}

// Decoded at module load so the ~30 ms cost lands in Worker startup, not in a request's CPU budget.
load();

/** true on mapped land, false on water, null outside the mask area (or for NaN): unknown. */
export function isLand(lat, lon) {
  const r = Math.floor((north - lat) / CELL);
  const c = Math.floor((lon - west) / CELL);
  if (!(r >= 0 && r < ROWS && c >= 0 && c < COLS)) return null; // also rejects NaN
  let crossings = 0;
  for (let i = rowStart[r]; i < rowStart[r + 1] && bounds[i] <= c; i++) crossings++;
  return (crossings & 1) === 1;
}

// First sampled land cell along the segment. Returns { conflict, clear } where
// conflict is null when the start is on land (coastline imperfect near ports) or when the path
// leaves the mask area before any land sample (unknown, never reported as clear),
// and clear is the fraction (0..1) of the segment up to the last water sample before land.
// ponytail: point sampling every stepMeters; islets thinner than the step can be missed.
function scan(lat1, lon1, lat2, lon2, stepMeters) {
  if (isLand(lat1, lon1) !== false) return { conflict: null, clear: null };
  const dy = (lat2 - lat1) * 111111;
  const dx = (lon2 - lon1) * 111111 * Math.cos((lat1 + lat2) / 2 * Math.PI / 180);
  const n = Math.max(1, Math.ceil(Math.hypot(dx, dy) / stepMeters));
  for (let i = 1; i <= n; i++) {
    const t = i / n;
    const land = isLand(lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t);
    if (land === null) return { conflict: null, clear: null };
    if (land) return { conflict: true, clear: (i - 1) / n };
  }
  return { conflict: false, clear: null };
}

/** true / false, or null when unresolved: start on land, or the path leaves the mask area before any land. */
export function pathHitsLand(lat1, lon1, lat2, lon2, stepMeters = 100) {
  return scan(lat1, lon1, lat2, lon2, stepMeters).conflict;
}

/** Fraction (0..1) of the segment before the first land sample; null if none or unresolved. */
export function clearUntilFraction(lat1, lon1, lat2, lon2, stepMeters = 100) {
  return scan(lat1, lon1, lat2, lon2, stepMeters).clear;
}

export const maskInfo = { bbox: mask.bbox, cell_deg: CELL, cols: COLS, rows: ROWS, licence: mask.licence };
