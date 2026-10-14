"""Reject empty, skipped, or unsuccessful JUnit reports from required CI suites."""
import sys
import xml.etree.ElementTree as ET


def check(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter('testcase'))
    counts = {name: sum(case.find(name) is not None for case in cases)
              for name in ('skipped', 'failure', 'error')}
    print(f'{path}: {len(cases)} tests, {counts}')
    return bool(cases) and not any(counts.values())


if __name__ == '__main__':
    results = [check(path) for path in sys.argv[1:]]
    sys.exit(0 if results and all(results) else 1)
