import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

test('versioned land mask has intact bytes, metadata, dimensions and row encoding', () => {
  const bytes = readFileSync(new URL('../cloudflare/land_mask.json', import.meta.url));
  assert.equal(createHash('sha256').update(bytes).digest('hex'),
    '9154aea90f28a1ec87f017335a44fe48cf736910a1ec1abf513ef3cba6ac7f41');
  const mask = JSON.parse(bytes);
  assert.deepEqual(mask.bbox, { west: 9, south: 53.5, east: 31, north: 66 });
  assert.equal(mask.cell_deg, .001);
  assert.equal(mask.cols, 22000); assert.equal(mask.rows, 12500);
  assert.equal(mask.row_order, 'north_to_south'); assert.equal(mask.licence, 'ODbL 1.0');
  assert.equal(mask.source_data_date, '2026-10-13T00:00:00Z');
  assert.match(mask.attribution, /OpenStreetMap contributors/);
  const data = Buffer.from(mask.data, 'base64');
  assert.equal(data.toString('base64'), mask.data, 'canonical base64');
  let position = 0;
  function integer() {
    let value = 0;
    for (let shift = 0; shift <= 28; shift += 7) {
      assert.ok(position < data.length, 'complete varint');
      const byte = data[position++];
      value += (byte & 127) * 2 ** shift;
      if (byte < 128) return value;
    }
    assert.fail('oversized varint');
  }
  let landCells = 0;
  for (let row = 0; row < mask.rows; row++) {
    const count = integer();
    assert.ok(count <= mask.cols + 1, 'bounded row runs');
    let total = 0;
    for (let run = 0; run < count; run++) {
      const length = integer(); total += length;
      assert.ok(total <= mask.cols, 'runs fit row');
      if (run % 2) landCells += length;
    }
    if (count % 2) landCells += mask.cols - total;
  }
  assert.equal(position, data.length, 'no trailing or missing rows');
  assert.equal(Math.round(landCells / (mask.cols * mask.rows) * 10000) / 10000, mask.land_fraction);
});
