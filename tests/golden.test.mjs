import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import worker from '../cloudflare/worker.mjs';

const read = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const raw = read('./fixtures/raw-ais-v1.json');
const golden = read('./golden/vessels-v1.json');
const { now } = read('./fixtures/cases-v1.json');

function harness(t) {
  let requestTime = now;
  t.mock.method(Date, 'now', () => requestTime);
  t.mock.method(globalThis, 'fetch', async () => Response.json(raw));
  const cache = new Map();
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'caches');
  Object.defineProperty(globalThis, 'caches', { configurable: true, value: { default: {
    async match(key) { return cache.get(key.url)?.clone(); },
    async put(key, value) { cache.set(key.url, value.clone()); },
  } } });
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, 'caches', previous);
    else delete globalThis.caches;
  });
  return {
    advance(ms) { requestTime += ms; },
    request(path) {
      return worker.fetch(new Request(`https://golden.test${path}`), {}, { waitUntil() {} });
    },
  };
}

function compare(actual, expected) {
  assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort(), 'complete API field set');
  for (const [key, value] of Object.entries(expected)) {
    if (key === 'predicted_latitude' || key === 'predicted_longitude') {
      if (value === null) assert.equal(actual[key], null, key);
      else assert.ok(Math.abs(actual[key] - value) < 1e-9, `${key}: ${actual[key]} != ${value}`);
    } else assert.deepEqual(actual[key], value, `${expected.vessel_id}.${key}`);
  }
}

test('raw AIS pipeline matches independently calculated complete versioned output', async t => {
  const h = harness(t);
  const response = await h.request('/vessels?limit=1000');
  assert.equal(response.status, 200);
  const vessels = await response.json();
  assert.equal(vessels.length, golden.length);
  vessels.forEach((vessel, index) => compare(vessel, golden[index]));
});

test('detail and JSON export preserve the full golden projection contract', async t => {
  const h = harness(t);
  const exported = await (await h.request('/vessels/download')).json();
  assert.equal(exported.length, golden.length);
  exported.forEach((vessel, index) => compare(vessel, golden[index]));
  for (const expected of golden) {
    compare(await (await h.request(`/vessels/${expected.vessel_id}`)).json(), expected);
  }
});

test('cached observations that expire do not yield fabricated forecasts', async t => {
  const h = harness(t);
  await h.request('/vessels?limit=1000');
  h.advance(2);
  const vessels = await (await h.request('/vessels?limit=1000')).json();
  assert.equal(vessels.length, golden.length - 1);
  assert.equal(vessels.some(v => v.vessel_id === 230000019), false);
  const noMotion = vessels.find(v => v.vessel_id === 230000023);
  compare(noMotion, golden.find(v => v.vessel_id === 230000023));
});
