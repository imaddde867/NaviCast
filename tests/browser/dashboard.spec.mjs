import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';

const now = Date.UTC(2026, 9, 14, 12);
const metadata = { mode: 'live', prediction_method: 'dead_reckoning',
  prediction_horizon_minutes: 30, observation_stale_after_seconds: 300 };
const leaflet = new URL('../../node_modules/leaflet/dist/', import.meta.url);
const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jA8sAAAAASUVORK5CYII=', 'base64');

test.beforeEach(async ({ page }) => {
  await page.coverage.startJSCoverage({ resetOnNavigation: false });
});
test.afterEach(async ({ page }, info) => {
  const entries = await page.coverage.stopJSCoverage();
  mkdirSync(info.outputDir, { recursive: true });
  writeFileSync(info.outputPath('js-coverage.json'), JSON.stringify(entries));
});

function vessel(id = 230000001, changes = {}) {
  return { vessel_id: id, current_latitude: 59.5, current_longitude: 20,
    current_timestamp: new Date(now - 60_000).toISOString(), sog: 8, cog: 0, heading: null,
    country: 'Finland', vessel_type: 'Cargo', pos_acc: true, data_source: 'ais',
    predicted_latitude: null, predicted_longitude: null, prediction_for_timestamp: null,
    prediction_made_at: null, prediction_method: null, projection_land_conflict: null,
    projection_clear_until_fraction: null, ...changes };
}
const projected = changes => vessel(230000001, { predicted_latitude: 59.56667149, predicted_longitude: 20,
  prediction_for_timestamp: new Date(now + 29 * 60_000).toISOString(),
  prediction_made_at: new Date(now).toISOString(), prediction_method: 'dead_reckoning',
  projection_land_conflict: false, ...changes });

async function dashboard(page, data, meta = metadata) {
  const state = { data, meta, status: 200, calls: [], errors: [] };
  page.on('pageerror', error => state.errors.push(error.message));
  await page.clock.install({ time: new Date(now) });
  await page.clock.pauseAt(new Date(now));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.hostname === '127.0.0.1') {
      if (url.pathname === '/meta') return route.fulfill({ json: state.meta });
      if (url.pathname === '/vessels') {
        state.calls.push(url.searchParams.get('limit'));
        return route.fulfill({ status: state.status, json: state.status === 200 ? state.data : { detail: 'Unavailable' } });
      }
      return route.continue();
    }
    if (url.hostname === 'unpkg.com') {
      const file = url.pathname.endsWith('.js') ? 'leaflet.js' : 'leaflet.css';
      return route.fulfill({ body: readFileSync(new URL(file, leaflet)),
        contentType: file.endsWith('.js') ? 'text/javascript' : 'text/css',
        headers: { 'Access-Control-Allow-Origin': '*' } });
    }
    if (url.pathname.endsWith('.png')) return route.fulfill({ body: tile, contentType: 'image/png' });
    return route.fulfill({ body: '', contentType: 'text/css' });
  });
  await page.goto('/');
  return state;
}

// Read real Leaflet objects: no fake map, no injected application functions.
const layers = page => page.evaluate(() => {
  const result = { actual: 0, endpoints: 0, lines: [] };
  map.eachLayer(layer => {
    if (layer instanceof L.Polyline) result.lines.push({ points: layer.getLatLngs().map(p => [p.lat, p.lng]),
      color: layer.options.color, dash: layer.options.dashArray });
    if (layer instanceof L.CircleMarker) {
      if (layer.options.className?.includes('vessel-prediction')) result.endpoints++;
      else result.actual++;
    }
  });
  return result;
});
async function loaded(page, count = 1) {
  await expect(page.locator('#vessel-count')).toHaveText(String(count));
  await page.clock.fastForward(1000);
  await expect(page.getByRole('status', { name: 'Loading vessel data' })).toBeHidden();
  await expect(page.locator('#map canvas').first()).toBeVisible();
  await expect.poll(() => page.evaluate(() => {
    const canvas = document.querySelector('#map canvas');
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    return pixels.some((value, index) => index % 4 === 3 && value > 0);
  })).toBe(true);
}
async function openVessel(page) {
  const point = await page.evaluate(() => {
    const p = map.latLngToContainerPoint([59.5, 20]);
    return { x: p.x, y: p.y };
  });
  await page.locator('#map').click({ position: point });
  await expect(page.locator('.leaflet-popup')).toBeVisible();
}

for (const [name, data] of [
  ['missing projection', vessel()],
  ['expired projection', projected({ prediction_for_timestamp: new Date(now - 1).toISOString() })],
  ['invalid projection', projected({ predicted_latitude: 91 })],
]) {
  test(`${name} never creates a substitute trajectory`, async ({ page }) => {
    const state = await dashboard(page, [data]);
    await loaded(page);
    expect(await layers(page)).toEqual({ actual: 1, endpoints: 0, lines: [] });
    await expect(page.locator('#prediction-count')).toHaveText('0');
    expect(state.calls).toEqual(['1000']);
    expect(state.errors).toEqual([]);
  });
}

test('valid projection renders its exact server trajectory and real popup', async ({ page }) => {
  const state = await dashboard(page, [projected()]);
  await loaded(page);
  const rendered = await layers(page);
  expect(rendered.actual).toBe(1); expect(rendered.endpoints).toBe(1);
  expect(rendered.lines).toHaveLength(1);
  expect(rendered.lines[0].points).toEqual([[59.5, 20], [59.56667149, 20]]);
  await expect(page.locator('#prediction-count')).toHaveText('1');
  const point = await page.evaluate(() => {
    const p = map.latLngToContainerPoint([59.5, 20]);
    const q = map.latLngToContainerPoint([59.56667149, 20]);
    return { x: p.x, y: p.y, overlap: p.distanceTo(q) };
  });
  expect(point.overlap).toBeLessThan(6.75); // centre click must land inside the endpoint hit area (radius 6 + half stroke), else #43 is not covered
  await page.locator('#map').hover({ position: point });
  expect(await page.evaluate(() => vessels.get(230000001).predictionLine.options.weight)).toBe(3);
  await openVessel(page);
  await expect(page.locator('.leaflet-popup')).toContainText('Constant-course projection · 30 min');
  await expect(page.locator('.leaflet-popup')).toContainText('230000001');
  expect(state.errors).toEqual([]);
});

test('mobile centre tap opens the vessel popup beneath a projection endpoint', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  const page = await context.newPage();
  try {
    await dashboard(page, [projected()]);
    await loaded(page);
    const point = await page.evaluate(() => {
      const p = map.latLngToContainerPoint([59.5, 20]);
      const rect = document.getElementById('map').getBoundingClientRect();
      return { x: rect.left + p.x, y: rect.top + p.y };
    });
    await page.touchscreen.tap(point.x, point.y);
    await expect(page.locator('.leaflet-popup')).toContainText('230000001');
  } finally {
    await context.close();
  }
});

test('projection removed on the next actual poll clears line and endpoint', async ({ page }) => {
  const state = await dashboard(page, [projected()]);
  await loaded(page);
  expect((await layers(page)).endpoints).toBe(1);
  state.data = [vessel()];
  await page.clock.fastForward(10_000);
  await expect.poll(() => state.calls.length).toBe(2);
  await expect.poll(async () => (await layers(page)).endpoints).toBe(0);
  expect((await layers(page)).lines).toEqual([]);
  await expect(page.locator('#prediction-count')).toHaveText('0');
});

test('server land warning and grey dashed rendering survive in the real map', async ({ page }) => {
  await dashboard(page, [projected({ projection_land_conflict: true, projection_clear_until_fraction: .644 })]);
  await loaded(page);
  const rendered = await layers(page);
  expect(rendered.lines[0]).toMatchObject({ color: '#8a8a8a', dash: '2,8' });
  expect(rendered.endpoints).toBe(1);
  await openVessel(page);
  await expect(page.locator('.leaflet-popup')).toContainText('Coast ahead: straight-line estimate crosses land');
});

for (const count of [600, 1000]) {
  test(`${count} API records disclose both map and API limits correctly`, async ({ page }) => {
    const state = await dashboard(page, Array.from({ length: count }, (_, i) => vessel(230000001 + i)));
    await loaded(page, count);
    expect((await layers(page)).actual).toBe(500);
    await expect(page.getByRole('button', { name: 'All on map (500)', exact: true })).toBeVisible();
    const notice = page.getByRole('status').filter({ hasText: `Map displays 500 of ${count}` });
    await expect(notice).toBeVisible();
    await expect(notice).toContainText('500-vessel map limit');
    if (count === 1000) await expect(notice).toContainText('full fleet may be larger');
    else await expect(notice).not.toContainText('full fleet may be larger');
    expect(state.calls).toEqual(['1000']);
  });
}

test('invalid metadata never guesses configuration or requests forecasts', async ({ page }) => {
  const state = await dashboard(page, [projected()], { mode: 'live' });
  await expect(page.getByRole('status').filter({ hasText: 'Feed configuration unavailable' })).toBeVisible();
  expect(await layers(page)).toEqual({ actual: 0, endpoints: 0, lines: [] });
  expect(state.calls).toEqual([]);
  state.meta = metadata;
  await page.clock.fastForward(10_000);
  await expect.poll(() => state.calls.length).toBe(1);
  await expect(page.locator('#prediction-count')).toHaveText('1');
});

test('API errors are visible and exponential retry recovers', async ({ page }) => {
  const state = await dashboard(page, [vessel()]);
  await loaded(page);
  state.status = 503;
  await page.clock.fastForward(10_000);
  await expect(page.getByRole('status').filter({ hasText: 'Retrying in 10s' })).toBeVisible();
  await page.clock.fastForward(10_000);
  await expect(page.getByRole('status').filter({ hasText: 'Retrying in 20s' })).toBeVisible();
  const requests = state.calls.length;
  await page.clock.fastForward(10_000);
  expect(state.calls).toHaveLength(requests);
  state.status = 200;
  await page.clock.fastForward(10_000);
  await expect.poll(() => state.calls.length).toBe(requests + 1);
  await expect(page.locator('#fetch-error')).toBeHidden();
});

test('filters, markers, popup escaping and counts stay consistent', async ({ page }) => {
  await dashboard(page, [projected(), vessel(230000002, { sog: 0, current_longitude: 20.1 }),
    vessel(230000003, { sog: null, cog: null, current_longitude: 20.2, country: '<img src=x onerror=alert(1)>' })]);
  await loaded(page, 3);
  await page.getByRole('button', { name: 'Stationary (1)', exact: true }).click();
  expect((await layers(page)).actual).toBe(1);
  expect((await layers(page)).endpoints).toBe(0);
  await expect(page.locator('#feed-status')).toContainText('1 vessels visible');
  await page.getByRole('button', { name: 'Projected (1)', exact: true }).click();
  expect((await layers(page)).actual).toBe(1);
  expect((await layers(page)).endpoints).toBe(1);
  await page.getByText('Show projections', { exact: true }).click();
  expect((await layers(page)).endpoints).toBe(0);
  await page.getByRole('button', { name: 'All on map (3)', exact: true }).click();
  expect((await layers(page)).actual).toBe(3);
  const point = await page.evaluate(() => { const p = map.latLngToContainerPoint([59.5, 20.2]); return { x: p.x, y: p.y }; });
  await page.locator('#map').click({ position: point });
  await expect(page.locator('.leaflet-popup')).toContainText('<img src=x onerror=alert(1)>');
  await expect(page.locator('.leaflet-popup img')).toHaveCount(0);
});

test('mobile navigation disclaimer and essential controls are visible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await dashboard(page, [vessel()]);
  await loaded(page);
  await expect(page.getByText('Not for navigation · illustrative estimates only', { exact: true })).toBeInViewport();
  await expect(page.getByRole('button', { name: 'Toggle map settings' })).toBeInViewport();
  await page.getByRole('button', { name: 'Toggle map settings' }).click();
  await expect(page.getByRole('button', { name: 'All on map (1)', exact: true })).toBeInViewport();
  await expect(page.getByRole('button', { name: 'Center on Finland' })).toBeInViewport();
  await expect(page.getByText('Show projections', { exact: true })).toBeInViewport();
  await expect(page.getByLabel('Show projections', { exact: true })).toBeAttached();
});
