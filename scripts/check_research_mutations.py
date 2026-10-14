"""Demonstrate scientific regressions in temporary copies, without bytecode reuse."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'research'
mutations = [
    ('row bootstrap', 'uncertainty.py',
     'indexes = np.concatenate([clusters[index] for index in rng.integers(len(clusters), size=len(clusters))])',
     'indexes = rng.integers(len(mmsi), size=len(mmsi))'),
    ('purge omitted', 'splits.py',
     'if target < validation_start - purge_ms:', 'if origin < validation_start:'),
    ('matching tolerance drift', 'evaluate.py', 'TOLERANCE_MS = 60_000', 'TOLERANCE_MS = 60_001'),
]
with tempfile.TemporaryDirectory(prefix='navicast-science-mutations-') as directory:
    copy = Path(directory)
    for name in ('test_validation.py', 'evaluate.py', 'splits.py', 'uncertainty.py'):
        shutil.copy(root / name, copy / name)

    def run():
        # Same-length, same-second edits can otherwise reuse stale .pyc files.
        return subprocess.run([sys.executable, '-B', '-m', 'pytest', 'test_validation.py', '-q'],
                              cwd=copy, capture_output=True, text=True, timeout=30,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    result = run()
    assert result.returncode == 0 and ' passed' in result.stdout, result.stdout + result.stderr
    assert not any(word in result.stdout for word in (' skipped', ' xfailed', ' deselected'))
    for label, name, before, after in mutations:
        original = (root / name).read_text()
        assert original.count(before) == 1, f'{label}: exactly one mutation site'
        (copy / name).write_text(original.replace(before, after))
        result = run()
        assert result.returncode == 1 and ' failed' in result.stdout, result.stdout + result.stderr
        print(f'DETECTED: {label}')
        (copy / name).write_text(original)
