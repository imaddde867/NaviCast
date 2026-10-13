#!/usr/bin/env python3
"""Write fake minute snapshots (same layout/schema as the R2 archive) for demos and tests.

    python research/make_synthetic.py OUT_DIR [--minutes 45]
"""
import argparse
import gzip
import json
import math
import os
from datetime import datetime, timezone

START_MS = 1_791_800_000_000 // 60_000 * 60_000
DEFAULT_VESSELS = [  # mmsi, lat, lon, sog kn, cog deg, turn deg/min
    dict(mmsi=230000001, lat=60.0, lon=24.0, sog=12.0, cog=90.0, turn=0.0),
    dict(mmsi=230000002, lat=59.5, lon=22.0, sog=6.0, cog=45.0, turn=0.0),
    dict(mmsi=230000003, lat=60.5, lon=25.0, sog=20.0, cog=200.0, turn=0.0),
    dict(mmsi=230000004, lat=60.2, lon=23.0, sog=10.0, cog=0.0, turn=3.0),  # turning
    dict(mmsi=230000005, lat=60.1, lon=21.0, sog=102.3, cog=360.0, turn=0.0),  # sentinel: not scored
]


def make(out_dir, minutes=45, vessels=None, start_ms=START_MS):
    vessels = [dict(v) for v in (DEFAULT_VESSELS if vessels is None else vessels)]
    paths = []
    for m in range(minutes):
        now = start_ms + m * 60_000
        rows = []
        for i, v in enumerate(vessels):
            rows.append(dict(mmsi=v["mmsi"], lat=v["lat"], lon=v["lon"], timestampExternal=now - 5_000 * i,
                             age_s=5 * i, sog=v["sog"], cog=v["cog"], heading=511, rot=0, navStat=0,
                             posAcc=True, raim=False))
            if v["sog"] < 102.3:  # move one minute along the current course, then turn
                d, rad = v["sog"] * 0.51444 * 60, math.radians(v["cog"])
                v["lat"] += d * math.cos(rad) / 111111
                v["lon"] += d * math.sin(rad) / (111111 * math.cos(math.radians(v["lat"])))
                v["cog"] = (v["cog"] + v["turn"]) % 360
        t = datetime.fromtimestamp(now / 1000, tz=timezone.utc)
        path = os.path.join(out_dir, "ais", t.strftime("%Y/%m/%d/%H"), t.strftime("%M") + ".ndjson.gz")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        header = dict(schema=1, fetched_at=t.isoformat().replace("+00:00", "Z"), source="synthetic", count=len(rows))
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write("\n".join(json.dumps(r) for r in [header, *rows]) + "\n")
        paths.append(path)
    return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--minutes", type=int, default=45)
    args = ap.parse_args()
    print(f"wrote {len(make(args.out_dir, args.minutes))} snapshots to {args.out_dir}")
