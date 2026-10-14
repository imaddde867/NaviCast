"""Fail for increased uncovered counts or absent required production coverage."""
import argparse
import json
from pathlib import Path


def read_report(kind, path):
    if kind == 'python':
        return {name: {'missing_statements': row['summary']['missing_lines'],
                       'missing_branches': row['summary']['missing_branches']}
                for name, row in json.loads(path.read_text())['files'].items()}
    if kind == 'browser':
        row = json.loads(path.read_text())
        return {row['file']: row}
    result = {}
    row = {}
    for line in path.read_text().splitlines():
        if line.startswith('SF:'):
            name = line[3:]
            row = {}
        elif line == 'end_of_record':
            result[name] = {'missing_lines': row['LF'] - row['LH'],
                            'missing_branches': row['BRF'] - row['BRH']}
        elif line.startswith(('LF:', 'LH:', 'BRF:', 'BRH:')):
            key, value = line.split(':')
            row[key] = int(value)
    return result


def check(actual, baseline):
    ok = True
    for name, limits in baseline.items():
        for metric, limit in limits.items():
            value = actual.get(name, {}).get(metric)
            passed = isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= limit
            print(f'{name}: {metric}={value}, baseline={limit}: {"PASS" if passed else "FAIL"}')
            ok &= passed
    return ok


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['python', 'node', 'browser'])
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root / 'tests/coverage-baseline.json').read_text())[args.kind]
    raise SystemExit(0 if check(read_report(args.kind, args.report), baseline) else 1)
