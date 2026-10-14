# Projection contract v1

`vessels-v1.json` is a complete expected `/vessels?limit=1000` response for
`../fixtures/raw-ais-v1.json` at **2026-10-14T12:00:00.000Z**. Inputs are
synthetic and contain no real vessel identities, names, destinations or tracks.
Sequential fabricated MMSIs are needed to verify deduplication, country lookup,
detail matching and output identity. Retained raw fields: type, coordinates,
MMSI, observation timestamp, speed/course, heading, navigation status and
position accuracy. One case supplies fake forecast fields to prove they are
ignored. `cases-v1.json` lists every scenario and the fixed clock.

## Independent calculations

These references were calculated in a separate Python/Decimal program without
importing or executing Worker, Python prediction or landmask code. They were
**not recorded from API output**. There is no snapshot-update command.

The registered software contract is planar constant speed/course with
0.51444 metres/second per knot, 111111 metres per latitude degree, longitude
scale multiplied by cosine(latitude), and a 1,800-second horizon. For example,
8 knots north gives 7407.936 metres, or exactly
`0.06667149067149067149067149067` degrees at that scale. Thus case 1 ends at
58.56667149067149 N, 20 E at 12:29 UTC. Numerical coordinate comparisons allow
1e-9 degrees for floating-point evaluation order; all other fields and nulls
are exact. This validates the specified approximation, not geodesic accuracy.

Coastline references use an independent Python LEB128 decoder, row boundaries
and binary search over the committed OSM raster, rather than `scanPath()`.
The same documented 100-metre sampling rule was independently calculated.
The Gotland case travels 27779.76 metres east, takes 278 sample intervals, and
the last water sample is 179/278 of the path: the API's rounded clear fraction
is **0.644**. Open Baltic water gives false/null; a Helsinki land start and a
start north of 66 N both give null/null. The asset's ODbL licence and attribution
remain applicable. These are raster-contract expectations, not independent
proof that the coastline asset matches physical geography.

Missing/invalid motion, low speed, excessive displacement and out-of-region
endpoints have all seven forecast/land fields null. AIS records at exactly
30 minutes old and future-dated records are excluded. One millisecond younger
is retained; it expires on a subsequent cache hit. Invalid coordinates and
IDs are rejected. The latest duplicate wins. List, detail and JSON export all
compare the full field set to these references.

## Review and changes

The golden values are **proposed for independent PR review**, not yet owner
approved. A separate review independently recalculated all 23 accepted vessels,
selection/deduplication, motion/time/null fields and raster flags; all agreed,
including Gotland 0.644. Owner approval remains a PR gate. Review arithmetic,
scenario classifications and null semantics before
merging. A requirement change must update this explanation and version the
fixture/expected pair; never regenerate goldens by running the implementation.
The existing 748-vessel snapshot remains useful for aggregate audit evidence,
but its server-generated endpoints are not used as correctness oracles.

Run `npm test` and `node scripts/check_projection_mutations.mjs`. The mutation
check copies sources into a disposable temporary directory, requires the
unmodified golden suite to pass, then requires assertion failures for invalid
speed admission, a changed horizon, suppressed land conflict and fabricated
null projection. It also asserts all three golden tests execute, so startup
failure cannot masquerade as mutation detection. It never alters a working
branch. Mutation evidence protects these software requirements; it does not
establish forecasting skill or complete coastline correctness.
