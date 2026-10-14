#!/usr/bin/env bash
set -euo pipefail
container_id=$(docker run -d -e NAVICAST_MODE=demo -p 127.0.0.1::8000 "${1:-navicast-check}")
trap 'docker logs "$container_id"; docker rm -f "$container_id" >/dev/null' EXIT
address=$(docker port "$container_id" 8000/tcp)
test -n "$address"
python3 - "http://$address" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

base = sys.argv[1]
def read(path):
    with urllib.request.urlopen(base + path, timeout=2) as response:
        assert response.status == 200
        return response.read()
def data(path):
    return json.loads(read(path))
for attempt in range(30):
    try:
        meta = data('/meta')
        break
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        if attempt == 29:
            raise
        time.sleep(.5)
assert meta['mode'] == 'demo'
assert data('/health')['status'] == 'healthy'
fleet = data('/vessels?limit=1000')
assert len(fleet) == 4, 'four deterministic demo vessels'
assert data(f"/vessels/{fleet[0]['vessel_id']}")['vessel_id'] == fleet[0]['vessel_id']
assert len(data('/vessels/download?format=json')) == len(fleet)
assert read('/vessels/download?format=csv').startswith(b'vessel_id,')
assert b'NAVICAST' in read('/')
print('Docker demo HTTP smoke passed: dashboard, metadata, health, list, detail and exports')
PY
