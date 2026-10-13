#!/usr/bin/env python3
"""Score position predictors against archived NaviCast AIS snapshots.

Input: a directory (searched recursively), glob or file of *.ndjson.gz snapshots
written by cloudflare/collector.mjs (schema 1, see docs/evaluation.md).
Requires: pip install numpy

    python research/evaluate.py ./archive --json out.json
"""
import argparse
import glob
import gzip
import json
import os
import sys
import zlib

import numpy as np

HORIZONS_MIN = (5, 10, 15, 30)
TOLERANCE_MS = 60_000
KN_TO_MS = 0.51444  # same constants as cloudflare/worker.mjs
M_PER_DEG = 111_111
EARTH_RADIUS_M = 6_371_008.8
BUCKETS = (("<2", 0.0, 2.0), ("2-8", 2.0, 8.0), (">=8", 8.0, np.inf))
PREDICTORS = ("persistence", "dead_reckoning")


def find_files(spec):
    if os.path.isdir(spec):
        spec = os.path.join(spec, "**", "*.ndjson.gz")
    return sorted(glob.glob(spec, recursive=True))


def load_tracks(paths):
    """mmsi -> arrays (t_ms, lat, lon, sog, cog) sorted by time, deduped by (mmsi, timestampExternal).

    ponytail: everything is held in memory (~100 B/obs); chunk by mmsi range if an archive outgrows RAM.
    """
    seen = {}
    for path in paths:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        r = json.loads(line)
                        ts = r["timestampExternal"]  # the header line has none -> KeyError
                        if ts is None:
                            continue
                        seen.setdefault(r["mmsi"], {}).setdefault(
                            int(ts), (r["lat"], r["lon"], r.get("sog"), r.get("cog")))
                    except (ValueError, KeyError, TypeError):
                        continue
        except (OSError, EOFError) as error:
            print(f"skipping {path}: {error}", file=sys.stderr)
    tracks = {}
    for mmsi, obs in seen.items():
        ts = sorted(obs)
        cols = np.array([[np.nan if v is None else v for v in obs[t]] for t in ts], dtype=float)
        tracks[mmsi] = (np.array(ts, dtype=np.int64), cols[:, 0], cols[:, 1], cols[:, 2], cols[:, 3])
    return tracks


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def dead_reckon(lat, lon, sog, cog, seconds):
    distance = sog * KN_TO_MS * seconds
    rad = np.radians(cog)
    return (lat + distance * np.cos(rad) / M_PER_DEG,
            lon + distance * np.sin(rad) / (M_PER_DEG * np.cos(np.radians(lat))))


def score(tracks):
    """horizon_min -> dict of equal-length arrays: sog, mmsi, t, persistence, dead_reckoning (metres)."""
    out = {h: {k: [] for k in ("sog", "mmsi", "t", *PREDICTORS)} for h in HORIZONS_MIN}
    for mmsi, (t, lat, lon, sog, cog) in tracks.items():
        valid = (sog >= 0.5) & (sog < 102.3) & (cog >= 0) & (cog < 360)  # NaN compares False
        if not valid.any():
            continue
        for h in HORIZONS_MIN:
            target = t + h * 60_000
            hi = np.clip(np.searchsorted(t, target), 0, len(t) - 1)
            lo = np.clip(hi - 1, 0, len(t) - 1)
            pick = np.where(np.abs(t[hi] - target) < np.abs(t[lo] - target), hi, lo)
            ok = valid & (np.abs(t[pick] - target) <= TOLERANCE_MS)
            if not ok.any():
                continue
            # dead reckoning projects over the real elapsed time to the matched observation
            plat, plon = dead_reckon(lat[ok], lon[ok], sog[ok], cog[ok], (t[pick][ok] - t[ok]) / 1000)
            truth_lat, truth_lon = lat[pick][ok], lon[pick][ok]
            rec = out[h]
            rec["persistence"].append(haversine_m(lat[ok], lon[ok], truth_lat, truth_lon))
            rec["dead_reckoning"].append(haversine_m(plat, plon, truth_lat, truth_lon))
            rec["sog"].append(sog[ok])
            rec["t"].append(t[ok])
            rec["mmsi"].append(np.full(ok.sum(), mmsi, dtype=np.int64))
    return {h: {k: np.concatenate(v) if v else np.array([]) for k, v in rec.items()} for h, rec in out.items()}


def summarize(scored):
    def pct(x):
        return {"median": float(np.median(x)), "p90": float(np.percentile(x, 90)),
                "p95": float(np.percentile(x, 95))} if len(x) else None
    result = {}
    for h, rec in scored.items():
        rows = {"all": np.ones(len(rec["sog"]), dtype=bool)}
        rows.update({name: (rec["sog"] >= lo) & (rec["sog"] < hi) for name, lo, hi in BUCKETS})
        result[str(h)] = {
            name: {"n": int(mask.sum()), **{p: pct(rec[p][mask]) for p in PREDICTORS}}
            for name, mask in rows.items()}
    return result


def group_id(mmsi, t_ms, split_by, n_groups=5):
    """Stub for future model training; nothing here trains. 'vessel' keeps every observation of a
    vessel in one group (no leakage across a vessel's track). 'time' returns the UTC day number,
    so the caller can put earlier days in train and later days in test."""
    if split_by == "vessel":
        return zlib.crc32(str(int(mmsi)).encode()) % n_groups
    return int(t_ms // 86_400_000)


def markdown(summary):
    fmt = lambda s, k: "-" if s is None else f"{s[k]:.0f}"
    lines = ["| horizon | sog (kn) | n | persistence median | p90 | p95 | dead_reckoning median | p90 | p95 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for h, rows in summary.items():
        for name, row in rows.items():
            p, d = row["persistence"], row["dead_reckoning"]
            lines.append(f"| {h} min | {name} | {row['n']} | " + " | ".join(
                [fmt(p, "median"), fmt(p, "p90"), fmt(p, "p95"), fmt(d, "median"), fmt(d, "p90"), fmt(d, "p95")]) + " |")
    return "\n".join(lines) + "\n\nErrors in metres.\n"


def evaluate(spec):
    paths = find_files(spec)
    tracks = load_tracks(paths)
    return {"files": len(paths), "vessels": len(tracks),
            "observations": sum(len(v[0]) for v in tracks.values()),
            "horizons": summarize(score(tracks))}, tracks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input", help="directory, glob or file of *.ndjson.gz snapshots")
    ap.add_argument("--json", metavar="FILE", help="also write the summary as JSON")
    ap.add_argument("--split-by", choices=("vessel", "time"),
                    help="stub: print the group assignment a future model split would use")
    args = ap.parse_args(argv)
    result, tracks = evaluate(args.input)
    if not result["files"] or not result["observations"]:
        print(f"no observations found under {args.input!r}", file=sys.stderr)
        return 2
    print(f"{result['files']} files, {result['vessels']} vessels, {result['observations']} unique observations\n")
    print(markdown(result["horizons"]))
    if args.split_by:
        groups = {}
        for mmsi, (t, *_) in tracks.items():
            for ts in t:
                g = group_id(mmsi, ts, args.split_by)
                groups[g] = groups.get(g, 0) + 1
        print(f"\nGroup assignment (--split-by {args.split_by}), observations per group:")
        print(", ".join(f"{g}: {n}" for g, n in sorted(groups.items())))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
