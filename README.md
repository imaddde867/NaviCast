# NaviCast

NaviCast is a FastAPI and Leaflet vessel map with a live AIS pipeline and a local demo. The demo serves four synthetic Baltic vessel records and 30-minute dead-reckoning estimates. It does not need a database, AIS feed, or trained model.

![NaviCast synthetic demo: Baltic vessel map and constant-course projections](docs/dashboard.png)

## Run the demo

With Docker:

```bash
docker compose up --build
```

Open <http://localhost:8000>. The API is available at `/vessels`, `/vessels/download`, `/vessels/{id}`, `/meta`, and `/health`.

Or run with Python 3.11+:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
NAVICAST_MODE=demo python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

## Run the live pipeline

The live profile starts PostgreSQL, the API, the Digitraffic MQTT client, and the prediction service. Copy `.env.example` to `.env`, set a local database password, then run:

```bash
docker compose --profile live up --build postgres api mqtt predictor
```

The live API is at <http://localhost:8001> by default. Set `LIVE_PORT` to change its host port. For local live mode, initialize your PostgreSQL database with `schema.sql`, set `NAVICAST_MODE=live` and the matching database settings in `.env`, then run `./start_navicast.sh`. The launcher loads the local shell configuration and checks the database before starting services.

The demo is the default Compose service. The live command above names the live services explicitly. The example database password is for local development only.

## Verify

```bash
pip install -r requirements-dev.txt
python -m pytest
node --test tests/frontend.test.cjs
```

For a running demo, `GET /meta` should report `mode: demo` and `prediction_method: dead_reckoning`; `GET /vessels` returns four records marked `data_source: synthetic`. In live mode, `/health` checks the database connection.

## Data and limits

- Demo positions and speeds are synthetic. Their timestamps are generated relative to the current time.
- Predictions are straight-line dead-reckoning estimates for 30 minutes. They are illustrative and must not be used for navigation or safety decisions.
- Live mode stores AIS data in PostgreSQL. Raw rows are cleaned up after 24 hours; expired projections are hidden immediately and stored predictions are cleaned up after one hour. Ingestion buffering is bounded and in memory: a prolonged database outage or process exit can lose observations.
- The API has no authentication. Keep live deployments on a trusted network.
- The map uses external Leaflet, icon, and tile services, so full map rendering needs browser network access.
- `ML_Model.ipynb` and `docs/ML_Model_docs/` contain historical research artifacts. They are not part of serving, and their results are not validated product-performance claims.

Optional database integration checks use `NAVICAST_TEST_DSN` pointing to a disposable PostgreSQL instance; they create session-local temporary tables. CI runs these checks with PostgreSQL 16.

The runtime is pinned in `requirements.lock`. Regenerate it with `uv pip compile requirements.txt --universal --python-version 3.11 -o requirements.lock` after reviewing dependency updates.

## Project files

- `docs/data_architecture.md` — demo and live data flows
- `docs/data_management_plan.md` — data fields, retention, and access limits
- `ML_Model.ipynb` — historical model exploration
- `LICENSE` — MIT license
