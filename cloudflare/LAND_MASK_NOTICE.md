# land_mask.json: OpenStreetMap data notice

`land_mask.json` is a derived database built from OpenStreetMap land polygons.

- Data: © OpenStreetMap contributors, https://www.openstreetmap.org/copyright
- Licence: Open Database License (ODbL) 1.0, https://opendatacommons.org/licenses/odbl/1-0/
- Source: `land-polygons-split-4326` from https://osmdata.openstreetmap.de/ (data date 2026-10-13)
- Changes: rasterised to a 0.001° land/water grid over 9–31°E, 53.5–66°N and run-length encoded by
  `scripts/build_land_mask.py`; inland lakes count as land. The file carries its own `licence` and
  `attribution` fields.

This file is made available under the ODbL 1.0, and any further derived database must keep that licence
and attribution. The rest of the repository is MIT (`LICENSE`) and is not covered by the ODbL.

The per-vessel `projection_land_conflict` flags that the API serves are produced from this database; the
map footer and `/docs` carry the OpenStreetMap attribution. The mask is approximate (a cell is land only when its centre is inside a polygon, so islets smaller
than a cell, about 110 m x 55 m at 60°N, can be absent; thin features can fall between the 100 m path
samples; port areas can be wrong), and the flags are not for
navigation. Whether publishing the flags as a Produced Work needs more than attribution is the repository
owner's call; this notice is not legal advice.
