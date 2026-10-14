"""Check deterministic mask rebuilding when the reviewed source ZIP is available."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def stable(path):
    value = json.loads(path.read_text())
    value.pop('built_at')  # Build time is the sole intentionally varying header field.
    return value


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    source = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='navicast-land-build-') as directory:
        outputs = [Path(directory) / f'mask-{index}.json' for index in range(2)]
        for output in outputs:
            subprocess.run([sys.executable, '-I', str(root / 'scripts/build_land_mask.py'),
                            '--zip', str(source), '--out', str(output)], check=True)
        assert stable(outputs[0]) == stable(outputs[1]), 'mask regeneration is not deterministic'
        assert stable(outputs[0]) == stable(root / 'cloudflare/land_mask.json'), 'source does not reproduce committed mask'
    print('Land mask regeneration is deterministic and matches the committed asset')
