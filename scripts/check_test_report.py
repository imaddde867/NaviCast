"""Reject empty, skipped, or unsuccessful JUnit reports from required CI suites."""
import argparse
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET


def check(path, required=()):
    root = ET.parse(path).getroot()
    cases = list(root.iter('testcase'))
    counts = {name: sum(case.find(name) is not None for case in cases)
              for name in ('skipped', 'failure', 'error')}
    identities = {f"{case.get('classname', '')}::{case.get('name', '')}" for case in cases}
    missing = set(required) - identities
    print(f'{path}: {len(cases)} tests, {counts}, {len(missing)} required cases missing')
    for name in sorted(missing):
        print(f'MISSING: {name}')
    return bool(cases) and not any(counts.values()) and not missing


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('inventory', type=Path, nargs='?')
    args = parser.parse_args()
    if os.getenv('NAVICAST_REQUIRED_TESTS') == '1' and args.inventory is None:
        parser.error('Required CI suites need an explicit testcase inventory')
    required = json.loads(args.inventory.read_text()) if args.inventory else ()
    if args.inventory and (not isinstance(required, list) or not required or not all(isinstance(name, str) for name in required)):
        parser.error('Required testcase inventory must be a nonempty list of identities')
    raise SystemExit(0 if check(args.report, required) else 1)
