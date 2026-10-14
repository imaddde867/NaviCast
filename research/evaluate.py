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

import numpy as np

HORIZONS_MIN = (5, 10, 15, 30)
TOLERANCE_MS = 60_000
KN_TO_MS = 0.51444  # same constants as cloudflare/worker.mjs
M_PER_DEG = 111_111
EARTH_RADIUS_M = 6_371_008.8
BUCKETS = (("<2", 0.0, 2.0), ("2-8", 2.0, 8.0), (">=8", 8.0, np.inf))
PREDICTORS = ("persistence", "dead_reckoning")
DIGITRAFFIC_SOURCE_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"
CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/"
ATTRIBUTION_MODIFICATIONS = [
    "Observations are deduplicated by MMSI and timestampExternal.",
    "Metrics are calculated after filtering invalid speed/course values and matching later observations to the requested horizons.",
]


def find_files(spec):
    if os.path.isdir(spec):
        spec = os.path.join(spec, "**", "*.ndjson.gz")
    return sorted(glob.glob(spec, recursive=True))


def load_tracks(paths, provenance=None):
    """mmsi -> arrays (t_ms, lat, lon, sog, cog) sorted by time, deduped by (mmsi, timestampExternal).

    ponytail: everything is held in memory (~100 B/obs); chunk by mmsi range if an archive outgrows RAM.
    """
    seen = {}
    for path in paths:
        source = None
        first_record = True
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        r = json.loads(line)
                        if first_record:
                            first_record = False
                            if isinstance(r, dict) and r.get("schema") == 1:
                                value = r.get("source")
                                if isinstance(value, str) and value.strip():
                                    source = value.strip()
                        ts = r["timestampExternal"]  # the header line has none -> KeyError
                        if ts is None:
                            continue
                        seen.setdefault(r["mmsi"], {}).setdefault(
                            int(ts), (r["lat"], r["lon"], r.get("sog"), r.get("cog")))
                    except (ValueError, KeyError, TypeError):
                        continue
        except (OSError, EOFError) as error:
            print(f"skipping {path}: {error}", file=sys.stderr)
        if provenance is not None:
            if source is None:
                provenance["missing_source_files"] += 1
            else:
                provenance["sources"].add(source)
    tracks = {}
    for mmsi, obs in seen.items():
        ts = sorted(obs)
        cols = np.array([[np.nan if v is None else v for v in obs[t]] for t in ts], dtype=float)
        tracks[mmsi] = (np.array(ts, dtype=np.int64), cols[:, 0], cols[:, 1], cols[:, 2], cols[:, 3])
    return tracks


def describe_provenance(provenance):
    sources = sorted(provenance["sources"])
    missing = provenance["missing_source_files"]
    digitraffic_url = DIGITRAFFIC_SOURCE_URL
    if not sources:
        status = "missing"
    elif len(sources) > 1 or missing:
        status = "mixed"
    elif sources[0] == digitraffic_url:
        status = "digitraffic"
    elif sources[0].casefold() == "synthetic":
        status = "synthetic"
    else:
        status = "identified"

    described_sources = []
    for source in sources:
        if source == digitraffic_url:
            described_sources.append({
                "source": "Fintraffic Digitraffic Marine AIS locations API",
                "source_url": digitraffic_url,
                "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
                "license_url": CC_BY_4_URL,
            })
        else:
            described_sources.append({"source": source})
    return {
        "status": status,
        "sources": described_sources,
        "files_without_source": missing,
        "modifications": ATTRIBUTION_MODIFICATIONS,
    }


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
    counts = {h: dict(origins=0, invalid_motion=0, unmatched_targets=0, matched=0) for h in HORIZONS_MIN}
    for mmsi, (t, lat, lon, sog, cog) in tracks.items():
        valid = (sog >= 0.5) & (sog < 102.3) & (cog >= 0) & (cog < 360)  # NaN compares False
        for h in HORIZONS_MIN:
            target = t + h * 60_000
            hi = np.clip(np.searchsorted(t, target), 0, len(t) - 1)
            lo = np.clip(hi - 1, 0, len(t) - 1)
            pick = np.where(np.abs(t[hi] - target) < np.abs(t[lo] - target), hi, lo)
            ok = valid & (np.abs(t[pick] - target) <= TOLERANCE_MS)
            counts[h]['origins'] += len(t)
            counts[h]['invalid_motion'] += int((~valid).sum())
            counts[h]['unmatched_targets'] += int((valid & ~ok).sum())
            counts[h]['matched'] += int(ok.sum())
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
    return {h: {**{k: np.concatenate(v) if v else np.array([]) for k, v in rec.items()},
                'accounting': counts[h]} for h, rec in out.items()}


def summarize(scored):
    def pct(x):
        x = x[np.isfinite(x)]
        return {"median": float(np.median(x)), "p90": float(np.percentile(x, 90)),
                "p95": float(np.percentile(x, 95))} if len(x) else None
    result = {}
    for h, rec in scored.items():
        rows = {"all": np.ones(len(rec["sog"]), dtype=bool)}
        rows.update({name: (rec["sog"] >= lo) & (rec["sog"] < hi) for name, lo, hi in BUCKETS})
        result[str(h)] = {
            name: {"n": int(mask.sum()),
                   "missing_predictions": {p: int((~np.isfinite(rec[p][mask])).sum()) for p in PREDICTORS},
                   "coverage": {p: float(np.isfinite(rec[p][mask]).mean()) if mask.any() else None for p in PREDICTORS},
                   **{p: pct(rec[p][mask]) for p in PREDICTORS}}
            for name, mask in rows.items()}
        result[str(h)]['all']['accounting'] = rec['accounting']
    return result


def markdown(summary):
    fmt = lambda s, k: "-" if s is None else f"{s[k]:.0f}"
    lines = ["| horizon | sog (kn) | matched n | persistence coverage | dead_reckoning coverage | persistence median | p90 | p95 | dead_reckoning median | p90 | p95 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for h, rows in summary.items():
        for name, row in rows.items():
            p, d = row["persistence"], row["dead_reckoning"]
            coverage = ' | '.join('-' if row['coverage'][p] is None else f"{row['coverage'][p]:.1%}" for p in PREDICTORS)
            lines.append(f"| {h} min | {name} | {row['n']} | {coverage} | " + " | ".join(
                [fmt(p, "median"), fmt(p, "p90"), fmt(p, "p95"), fmt(d, "median"), fmt(d, "p90"), fmt(d, "p95")]) + " |")
    return "\n".join(lines) + "\n\nErrors in metres.\n"


def evaluate(spec):
    paths = find_files(spec)
    provenance = {"sources": set(), "missing_source_files": 0}
    tracks = load_tracks(paths, provenance)
    return {"files": len(paths), "vessels": len(tracks),
            "observations": sum(len(v[0]) for v in tracks.values()),
            "horizons": summarize(score(tracks)),
            "evaluation_rules": {
                "version": "prototype-1", "validation_status": "unvalidated",
                "horizons_minutes": list(HORIZONS_MIN), "target_tolerance_ms": TOLERANCE_MS,
                "target_tie": "earlier", "projection_elapsed": "matched_observation",
                "percentile_method": "linear", "error_units": "metres",
                "earth_radius_m": EARTH_RADIUS_M, "knots_to_mps": KN_TO_MS,
                "metres_per_degree": M_PER_DEG, "production_caps": "not_applied",
                "prediction_population": "identical_matched_rows_with_counted_abstentions",
            },
            "data_attribution": describe_provenance(provenance)}, tracks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input", help="directory, glob or file of *.ndjson.gz snapshots")
    ap.add_argument("--json", metavar="FILE", help="also write the summary as JSON")
    args = ap.parse_args(argv)
    result, _tracks = evaluate(args.input)
    if not result["files"] or not result["observations"]:
        print(f"no observations found under {args.input!r}", file=sys.stderr)
        return 2
    print(f"{result['files']} files, {result['vessels']} vessels, {result['observations']} unique observations\n")
    print('Evaluation rule prototype-1: unvalidated; software/synthetic checks do not establish forecasting accuracy.')
    print(markdown(result["horizons"]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
