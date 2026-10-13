# Baseline (2026-10-13 10:30 UTC)

`vessels_2026-10-13T1030Z.json` — raw `GET /vessels?limit=1000` from navicast.imadlab.com (748 vessels, 171 with dead-reckoning projection).
`landcheck_ne10m.py` — tests each projection against Natural Earth 10m land (pyshp + shapely; expects `vessels.json` and `land/ne_10m_land.*` in cwd).

Result with Natural Earth 10m (coarse; 14 starts fall on land = coastline artifacts):
- endpoint on land: 18/171 (10.5%)
- path touches land: 31/171 (18.1%)
- started in water, path crosses land: 17/157 (10.8%)
- heading known 155, |heading-cog| > 30 deg: 8
- nav_stat of projected: 0:155, 3:5, 15:4, 1:2, 2:1, 5:1, 4:1, 10:1, 8:1 (3 anchored/moored)
- ship type known: 0/748; sog>=102 (invalid-ish): 2; cog missing: 41

Single snapshot, not a benchmark. Re-measure with a finer coastline before citing as acceptance criteria.

## Data attribution

AIS observations in the snapshot come from Fintraffic Digitraffic (https://www.digitraffic.fi/en/marine-traffic/), licensed CC BY 4.0. Source: Fintraffic / digitraffic.fi, retrieved 2026-10-13.
