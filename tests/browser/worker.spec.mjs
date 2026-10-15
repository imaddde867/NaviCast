import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { build } from 'esbuild';

test.afterEach(async ({ page }, info) => {
  mkdirSync(info.outputDir, { recursive: true });
  writeFileSync(info.outputPath('js-coverage.json'), JSON.stringify(await page.coverage.stopJSCoverage()));
});

// No browser interception of /meta or /vessels: only the Worker's upstream is replaced.
test('real Worker API drives the Chromium dashboard from raw AIS', async ({ page }) => {
  await page.coverage.startJSCoverage();
  const bundle = await build({ stdin: { contents: "export { default } from './cloudflare/worker.mjs';", resolveDir: process.cwd() }, bundle: true,
    write: false, format: 'esm', platform: 'browser' });
  let upstreamCalls = 0;
  const observedAt = Date.now() - 60_000;
  const runtime = new Miniflare(convertV4MiniflareOptions({ host: '127.0.0.1', port: 0, workers: [{ name: 'navicast', modules: true, script: bundle.outputFiles[0].text,
    compatibilityDate: '2026-10-13', unsafeDirectSockets: [{ host: '127.0.0.1', port: 0 }],
    serviceBindings: { ASSETS: request => {
      const path = new URL(request.url).pathname;
      return path === '/' ? new Response(readFileSync('static/index.html'),
        { headers: { 'Content-Type': 'text/html' } }) : new Response('', { status: 404 });
    } },
    outboundService(request) {
      expect(request.url).toBe('https://meri.digitraffic.fi/api/ais/v1/locations');
      upstreamCalls++;
      return Response.json({ type: 'FeatureCollection', features: [{ type: 'Feature',
        geometry: { type: 'Point', coordinates: [20, 59.5] },
        properties: { mmsi: 230000001, timestampExternal: observedAt,
          sog: 8, cog: 0, heading: 511, posAcc: true } }] });
    },
  }] }));
  try {
    await runtime.ready;
    const address = await runtime.unsafeGetDirectURL('navicast');
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route(url => url.origin !== address.origin, async route => {
      const url = new URL(route.request().url());
      if (url.hostname === 'unpkg.com') {
        const file = url.pathname.endsWith('.js') ? 'leaflet.js' : 'leaflet.css';
        return route.fulfill({ body: readFileSync(`node_modules/leaflet/dist/${file}`),
          contentType: file.endsWith('.js') ? 'text/javascript' : 'text/css',
          headers: { 'Access-Control-Allow-Origin': '*' } });
      }
      return route.fulfill({ body: '', contentType: 'text/css' });
    });
    const meta = page.waitForResponse(r => new URL(r.url()).pathname === '/meta');
    const fleet = page.waitForResponse(r => new URL(r.url()).pathname === '/vessels');
    await page.goto(address.href);
    expect((await meta).status()).toBe(200);
    expect(await (await meta).json()).toMatchObject({ prediction_method: 'dead_reckoning', prediction_horizon_minutes: 30 });
    const response = await fleet;
    expect(response.status()).toBe(200);
    expect(new URL(response.url()).search).toBe('?limit=1000');
    const [record] = await response.json();
    expect(record).toMatchObject({ vessel_id: 230000001, current_latitude: 59.5,
      current_longitude: 20, heading: null, country: 'Finland',
      prediction_method: 'dead_reckoning', projection_land_conflict: false });
    expect(record.predicted_latitude).toBeCloseTo(59.56667149067149, 10);
    expect(record.prediction_for_timestamp).toBe(new Date(observedAt + 30 * 60_000).toISOString());
    await expect(page.locator('#vessel-count')).toHaveText('1');
    await expect(page.locator('#prediction-count')).toHaveText('1');
    await expect(page.getByRole('status', { name: 'Loading vessel data' })).toBeHidden();
    await expect(page.locator('#map canvas').first()).toBeVisible();
    const rendered = await page.evaluate(() => {
      const result = { actual: 0, endpoints: 0, lines: [] };
      map.eachLayer(layer => {
        if (layer instanceof L.Polyline) result.lines.push(layer.getLatLngs().map(p => [p.lat, p.lng]));
        if (layer instanceof L.CircleMarker) {
          if (layer.options.className?.includes('vessel-prediction')) result.endpoints++;
          else result.actual++;
        }
      });
      return result;
    });
    expect(rendered).toEqual({ actual: 1, endpoints: 1,
      lines: [[[59.5, 20], [record.predicted_latitude, record.predicted_longitude]]] });
    expect(upstreamCalls).toBe(1);
    expect(errors).toEqual([]);
  } finally {
    await runtime.dispose();
  }
});
