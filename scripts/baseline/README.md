# Baseline (2026-10-13 10:30 UTC)

`vessels_2026-10-13T1030Z.json` — minimized and pseudonymized `GET /vessels?limit=1000` from navicast.imadlab.com (748 vessels, 171 with dead-reckoning projection).
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

## Fixture review

Retained fields: `vessel_id` (stable pseudonym, not MMSI), `current_latitude`, `current_longitude`, `current_timestamp`, `sog`, `cog`, `heading`, `nav_stat`, `vessel_type`, `predicted_latitude`, `predicted_longitude`. These support the coastline, motion, age and metadata checks in the baseline scripts. All other response fields are removed. Names, call signs and destinations are absent. Positions and timestamps remain real; pseudonymization does not guarantee anonymity.

Modifications: sorted MMSIs were replaced by sequential `vessel-*` identifiers and unused fields were removed. Position, motion, timestamp and projection values are unchanged. The data licence remains [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); source [Fintraffic / digitraffic.fi](https://www.digitraffic.fi/en/marine-traffic/). This review does not remove the original fixture from Git history.

Screenshot review: `docs/dashboard.png` shows explicitly synthetic demo positions and no vessel names or destinations. Historical model figures are confined to `archive/`; the portfolio screenshot is owner-reviewed outside this repository.

## Local collector CPU probe

Fetch a raw Digitraffic locations response to an untracked file outside the repo, then run:

```bash
node scripts/baseline/collector_cpu.mjs /path/to/cloudflare/collector.mjs /tmp/navicast-locations.json
```

The module can come from the PR #30 checkout. The probe includes parsing, record serialization and gzip, with a fake in-memory D1 binding (no network, no real D1); it checks the gzip header and row count. It reports dated CPU and elapsed measurements with a fixture checksum. Local Node results cannot establish compliance with Workers Free CPU accounting. The daily metadata invocation is not probed. Measure both crons after the owner deploys; do not infer approval to deploy or upgrade plans. Raw input must not be committed.
