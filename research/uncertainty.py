"""Paired median-error improvements with vessel-cluster bootstrap, never row draws."""
import numpy as np


def bootstrap_improvement(mmsi, baseline, candidate, *, seed, draws):
    mmsi, baseline, candidate = map(np.asarray, (mmsi, baseline, candidate))
    if any(array.ndim != 1 for array in (mmsi, baseline, candidate)) or not len(mmsi) or not (len(mmsi) == len(baseline) == len(candidate)):
        raise ValueError('Expected equal nonempty paired arrays')
    if not np.all(np.isfinite(baseline) & np.isfinite(candidate) & (baseline >= 0) & (candidate >= 0)):
        raise ValueError('Bootstrap requires finite, nonnegative paired errors')
    if not np.issubdtype(mmsi.dtype, np.integer) or np.any((mmsi <= 0) | (mmsi > 999999999)):
        raise ValueError('Invalid vessel identifiers')
    vessels = np.unique(mmsi)
    if len(vessels) < 2 or not isinstance(draws, int) or isinstance(draws, bool) or draws <= 0:
        raise ValueError('At least two vessels and positive draws required')
    clusters = [np.flatnonzero(mmsi == vessel) for vessel in vessels]
    rng = np.random.default_rng(seed)
    improvements = []
    for _ in range(draws):
        indexes = np.concatenate([clusters[index] for index in rng.integers(len(clusters), size=len(clusters))])
        improvements.append(float(np.median(baseline[indexes]) - np.median(candidate[indexes])))
    return {'improvement_m': float(np.median(baseline) - np.median(candidate)),
            'ci95_m': np.percentile(improvements, [2.5, 97.5]).tolist(),
            'vessels': len(vessels), 'draws': draws, 'weighting': 'per_observation', 'resampling': 'vessel'}
