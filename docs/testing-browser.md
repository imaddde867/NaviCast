# Chromium dashboard validation

Run `npm ci --ignore-scripts`, `npx playwright install chromium`, then
`npm run test:browser` (Python 3 is needed for the loopback static server).
Playwright 1.64.1 runs headless Chromium against the actual `static/index.html`.
The page still initializes the real Leaflet 1.9.4 map, canvas renderer, popup,
controls and timers. The thirteen isolated dashboard scenarios intercept API responses, provide the pinned Leaflet
distribution in place of the CDN response (preserving SRI), replace tiles with
a blank image and block other external resources. No live AIS/tile dependency.
Font Awesome is omitted; its icon rendering is not validated.

Thirteen dashboard cases cover missing/expired/invalid-coordinate forecasts, exact server
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
Popup tests click the current marker centre even where a projection endpoint
overlaps it. Projection lines and endpoints are noninteractive so vessel hover,
centre clicks and mobile taps reach the current marker; the vessel popup retains
the projection details. A mobile touch regression covers the same overlap.

Local baseline: 14 passed in 8.3 s, Node 26.10.0 (CI pins Node 22). Run
`node scripts/check_browser_mutations.mjs` to demonstrate detection of removing
the actual notice, requesting only 500 API rows and adding a browser prediction
fallback. The script requires a passing unmodified temporary copy and executed
browser assertion failures for each mutation. Working sources are untouched.

CI retains JUnit/HTML reports and failure screenshots/traces. It rejects skipped,
empty or unsuccessful required reports. The focused #42 branch used separate `browser.yml`; the combined #47
workflow consolidates `browser-e2e` into `ci.yml`.
No production service, browser login or deployment is involved.


A fourteenth scenario (`tests/browser/worker.spec.mjs`) sends Chromium requests
for `/meta` and `/vessels?limit=1000` to the production default Worker handler
running in local workerd. Only outbound AIS HTTP is replaced with a raw
GeoJSON observation (timestamped relative to test start); normalization,
metadata, projection, API serialization and Leaflet rendering run together.
The asset binding serves the unchanged dashboard HTML; CDN assets are supplied
locally and external presentation requests are blocked. This does not verify
Cloudflare's deployed asset router, live upstream availability or D1 persistence
(the runtime suite covers D1 separately).
