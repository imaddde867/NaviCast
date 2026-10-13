// Re-runs the baseline land check with the OSM land mask used by the Worker.
// Usage: node scripts/baseline/landcheck_mask.mjs [vessels.json]
import { readFileSync } from 'node:fs';
import { isLand, pathHitsLand, clearUntilFraction } from '../../cloudflare/landmask.mjs';

const file = process.argv[2] ?? new URL('./vessels_2026-10-13T1030Z.json', import.meta.url);
const projected = JSON.parse(readFileSync(file)).filter(v => v.predicted_latitude != null);
const pct = n => `${n}/${projected.length} (${(100 * n / projected.length).toFixed(1)}%)`;

// Same 100 m sampling as pathHitsLand, but counting a land start as "touching" so the
// number is comparable with the Natural Earth baseline (which includes coastline artifacts).
function touches(v) {
  const dy = (v.predicted_latitude - v.current_latitude) * 111111;
  const dx = (v.predicted_longitude - v.current_longitude) * 111111 * Math.cos(v.current_latitude * Math.PI / 180);
  const n = Math.max(1, Math.ceil(Math.hypot(dx, dy) / 100));
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    if (isLand(v.current_latitude + (v.predicted_latitude - v.current_latitude) * t,
      v.current_longitude + (v.predicted_longitude - v.current_longitude) * t)) return true;
  }
  return false;
}

let endLand = 0, touch = 0, startLand = 0, conflict = 0, clear = 0;
const fractions = [];
for (const v of projected) {
  const args = [v.current_latitude, v.current_longitude, v.predicted_latitude, v.predicted_longitude];
  if (isLand(v.predicted_latitude, v.predicted_longitude)) endLand++;
  if (touches(v)) touch++;
  const hit = pathHitsLand(...args);
  if (hit === null) startLand++;
  else if (hit) { conflict++; fractions.push(clearUntilFraction(...args)); }
  else clear++;
}
fractions.sort((a, b) => a - b);
console.log('projected vessels:', projected.length, 'of', JSON.parse(readFileSync(file)).length);
console.log('start on land (unresolved):', pct(startLand));
console.log('endpoint on land:', pct(endLand));
console.log('path touches land (incl. land starts):', pct(touch));
console.log('resolved (start in water):', projected.length - startLand,
  ' conflict true:', conflict, `(${(100 * conflict / (projected.length - startLand)).toFixed(1)}%)`, ' false:', clear);
if (fractions.length) console.log('clear-until fraction among conflicts: median', fractions[fractions.length >> 1].toFixed(2),
  'min', fractions[0].toFixed(2), 'max', fractions.at(-1).toFixed(2));
