"""Index splits for (MMSI, origin_ms, target_ms) windows; locked period is mandatory."""
from numbers import Integral

ROLES = ('train', 'validation', 'test')


def available(windows, locked_period):
    start, end = locked_period
    if not all(isinstance(v, Integral) and not isinstance(v, bool) for v in (start, end)) or start >= end:
        raise ValueError('Invalid locked period')
    result = []
    for index, (vessel, origin, target) in enumerate(windows):
        if not all(isinstance(v, Integral) and not isinstance(v, bool) for v in (vessel, origin, target)):
            raise ValueError('Window identifiers and times must be integers')
        if not 0 < vessel <= 999999999 or origin < 0 or target < origin:
            raise ValueError('Invalid prediction window')
        if not (origin < end and target >= start):
            result.append(index)
    return result


def vessel_split(windows, train, validation, test, *, locked_period):
    groups = dict(zip(ROLES, map(set, (train, validation, test))))
    if any(not isinstance(vessel, Integral) or isinstance(vessel, bool) or not 0 < vessel <= 999999999
           for group in groups.values() for vessel in group):
        raise ValueError('Invalid vessel identifiers')
    for i, role in enumerate(ROLES):
        if any(groups[role] & groups[other] for other in ROLES[i + 1:]):
            raise ValueError('A vessel belongs to multiple splits')
    split = {role: [] for role in ROLES}
    for index in available(windows, locked_period):
        assigned = [role for role in ROLES if windows[index][0] in groups[role]]
        if not assigned:
            raise ValueError('Unassigned vessel')
        split[assigned[0]].append(index)
    return split


def time_split(windows, *, validation_start, test_start, purge_ms, locked_period):
    if not all(isinstance(v, Integral) and not isinstance(v, bool) for v in (validation_start, test_start, purge_ms)):
        raise ValueError('Time boundaries must be integers')
    if not 0 <= validation_start < test_start or purge_ms < 0:
        raise ValueError('Invalid time boundaries or purge gap')
    split = {role: [] for role in ROLES}
    for index in available(windows, locked_period):
        _, origin, target = windows[index]
        if target < validation_start - purge_ms:
            split['train'].append(index)
        elif origin >= validation_start and target < test_start - purge_ms:
            split['validation'].append(index)
        elif origin >= test_start:
            split['test'].append(index)
    return split


def validate_split(windows, split, mode, *, locked_period, purge_ms):
    if (mode not in ('vessel', 'time') or set(split) != set(ROLES)
            or not isinstance(purge_ms, Integral) or isinstance(purge_ms, bool) or purge_ms < 0):
        raise ValueError('Invalid split policy')
    allowed = set(available(windows, locked_period))
    seen = set()
    for role in ROLES:
        for index in split[role]:
            if not isinstance(index, Integral) or isinstance(index, bool) or index not in allowed or index in seen:
                raise ValueError('Overlapping, invalid or locked split index')
            seen.add(index)
    for i, role in enumerate(ROLES):
        left = [windows[index] for index in split[role]]
        for other in ROLES[i + 1:]:
            right = [windows[index] for index in split[other]]
            if mode == 'vessel' and {row[0] for row in left} & {row[0] for row in right}:
                raise ValueError('vessel leakage across splits')
            if mode == 'time' and left and right and max(row[2] for row in left) + purge_ms >= min(row[1] for row in right):
                raise ValueError('target or purge-gap leakage across time splits')


def training_rows(windows, split, mode, *, locked_period, purge_ms):
    validate_split(windows, split, mode, locked_period=locked_period, purge_ms=purge_ms)
    return [windows[index] for index in split['train']]
