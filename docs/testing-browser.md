# Chromium dashboard validation

Run `npm ci --ignore-scripts`, `npx playwright install chromium`, then
`npm run test:browser` (Python 3 is needed for the loopback static server).
Playwright 1.64.1 runs headless Chromium against the actual `static/index.html`.
The page still initializes the real Leaflet 1.9.4 map, canvas renderer, popup,
controls and timers. Tests intercept API responses, provide the pinned Leaflet
distribution in place of the CDN response (preserving SRI), replace tiles with
a blank image and block other external resources. No live AIS/tile dependency.
Font Awesome is omitted; its icon rendering is not validated.

Twelve cases cover missing/expired/invalid-coordinate forecasts, exact server
trajectory and popup, next-poll deletion, land warning/style, 600/1,000 counts
and limits, invalid metadata/recovery, API exponential retry, filtering/escaping
and mobile controls/disclaimer. Assertions combine actual DOM/user actions,
real attached Leaflet layers, exact trajectory coordinates and nontransparent
canvas pixels. They do not manufacture missing elements. Prediction horizon
validation remains server-owned as required by #38; browser checks verify
coordinate plausibility, freshness and server-only output.

The first run found that selecting a filter updated map layers but left the
feed's visible count stale until the next timer. One line in the shared filter
handler now refreshes it immediately; the E2E assertion failed before the fix.
Popup tests click the exposed part of the current marker because nearby
projection endpoints can overlap it. Centre-click access with overlapping
markers remains a UX limitation, not an invented DOM workaround.

Local baseline: 12 passed in 4.8 s, Node 22.23.1. Run
`node scripts/check_browser_mutations.mjs` to demonstrate detection of removing
the actual notice, requesting only 500 API rows and adding a browser prediction
fallback. The script requires a passing unmodified temporary copy and executed
browser assertion failures for each mutation. Working sources are untouched.

CI retains JUnit/HTML reports and failure screenshots/traces. It rejects skipped,
empty or unsuccessful required reports. The focused #42 branch used separate `browser.yml`; the combined #47
workflow consolidates `browser-e2e` into `ci.yml`.
No production service, browser login or deployment is involved.
