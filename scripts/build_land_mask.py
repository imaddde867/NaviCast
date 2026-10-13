#!/usr/bin/env python3
"""Build cloudflare/land_mask.json: a run-length-encoded LAND/WATER raster of the
NaviCast operating region from OpenStreetMap land polygons (ODbL).

Build-time deps only (NOT in requirements*.txt):
    pip install numpy shapely pyogrio rasterio
Usage:
    python3 -I scripts/build_land_mask.py [--zip land-polygons-split-4326.zip] [--cell 0.001]
Downloads ~0.9 GB from osmdata.openstreetmap.de unless --zip is given.

A cell is land when its CENTRE lies inside an OSM land polygon. OSM land
polygons are derived from natural=coastline only, so inland lakes are LAND.

Asset format (cloudflare/land_mask.json):
    bbox, cell, cols, rows, source, licence ...  header fields
    data  base64 of: for each row (north->south, row 0 = bbox.north) a LEB128
          varint n, then n varint run lengths alternating water,land,water...
          starting with water (may be 0); the last run is implied by `cols`.
"""
import argparse, base64, datetime, json, os, re, tempfile, urllib.request, zipfile
import numpy as np, pyogrio, rasterio.features, shapely
from rasterio.transform import from_bounds

URL = 'https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip'
SHP = '/vsizip/{zip}/land-polygons-split-4326/land_polygons.shp'
WEST, EAST, SOUTH, NORTH = 9.0, 31.0, 53.5, 66.0
STRIP_ROWS = 500  # rasterise in horizontal strips to bound memory


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return out


def encode_row(row):
    change = np.flatnonzero(np.diff(row.astype(np.int8))) + 1  # indices where value flips
    bounds = np.concatenate(([0], change, [row.size]))
    runs = np.diff(bounds).tolist()
    if row[0]:           # row starts with land: emit zero-length water run first
        runs.insert(0, 0)
    runs = runs[:-1]     # last run implied
    return varint(len(runs)) + b''.join(varint(r) for r in runs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', help='local land-polygons-split-4326.zip (skips download)')
    ap.add_argument('--cell', type=float, default=0.001, help='cell size in degrees')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), '..', 'cloudflare', 'land_mask.json'))
    a = ap.parse_args()
    cols = round((EAST - WEST) / a.cell)
    rows = round((NORTH - SOUTH) / a.cell)
    with tempfile.TemporaryDirectory() as tmp:
        path = a.zip
        if not path:
            path = os.path.join(tmp, 'land.zip')
            with urllib.request.urlopen(URL) as r, open(path, 'wb') as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
        readme = zipfile.ZipFile(path).read('land-polygons-split-4326/README.txt').decode()
        data_date = re.search(r'Date of the data used is (\S+)', readme)
        encoded = bytearray()
        land_cells = 0
        for r0 in range(0, rows, STRIP_ROWS):
            r1 = min(rows, r0 + STRIP_ROWS)
            n, s = NORTH - r0 * a.cell, NORTH - r1 * a.cell
            _, _, wkb, _ = pyogrio.raw.read(SHP.format(zip=path), bbox=(WEST, s, EAST, n),
                                            columns=[], read_geometry=True)
            geoms = shapely.from_wkb(wkb)
            if len(geoms):
                strip = rasterio.features.rasterize(
                    ((g, 1) for g in geoms), out_shape=(r1 - r0, cols),
                    transform=from_bounds(WEST, s, EAST, n, cols, r1 - r0),
                    fill=0, all_touched=False, dtype='uint8').astype(bool)
            else:
                strip = np.zeros((r1 - r0, cols), bool)
            land_cells += int(strip.sum())
            for row in strip:
                encoded += encode_row(row)
            print(f'rows {r0}-{r1} of {rows}: {len(geoms)} polygons', flush=True)
    header = {
        'bbox': {'west': WEST, 'south': SOUTH, 'east': EAST, 'north': NORTH},
        'cell_deg': a.cell, 'cols': cols, 'rows': rows, 'row_order': 'north_to_south',
        'land_fraction': round(land_cells / (rows * cols), 4),
        'rule': 'cell is land when its centre is inside an OSM land polygon; inland lakes count as land',
        'source': 'OpenStreetMap land-polygons-split-4326 (osmdata.openstreetmap.de)',
        'source_data_date': data_date and data_date.group(1),
        'licence': 'ODbL 1.0',
        'attribution': '© OpenStreetMap contributors (ODbL) — https://www.openstreetmap.org/copyright',
        'built_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
        'encoding': 'rows north->south; per row LEB128 varint n then n varint run lengths alternating water,land,..; last run implied',
    }
    header['data'] = base64.b64encode(bytes(encoded)).decode()
    with open(a.out, 'w') as f:
        json.dump(header, f, separators=(',', ':'))
    print(f'wrote {a.out}: {len(encoded)} bytes raw runs, {os.path.getsize(a.out)} bytes json')


if __name__ == '__main__':
    main()
