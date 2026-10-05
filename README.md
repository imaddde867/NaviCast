# NAVICAST — Maritime Traffic Intelligence Platform

Real-time AIS vessel tracking + 30-minute trajectory prediction (ML with dead-reckoning fallback) for the Baltic Sea. MQTT ingest (Digitraffic feed) → PostgreSQL → FastAPI → Leaflet map.

## Demo

No live deployment. Quickstart follows — run it locally and open http://localhost:8000, where the map shows vessels with predicted tracks.

## Quickstart (reviewer path, no MQTT needed)

```bash
cp .env.example .env
docker compose up
```

This starts `postgres:16` (schema + `seed.sql` sample rows auto-loaded) and the API (`python:3.11-slim`, `pip install -r requirements.txt`, `uvicorn api_server:app`). Then:

- App: http://localhost:8000 (or `$PORT` if set: `${PORT:-8000}:8000`)
- Seeded check: `curl localhost:8000/vessels` → 200 with sample vessels. No MQTT feed required.

## Local setup (no Docker)

```bash
pip install -r requirements.txt
cp .env.example .env   # set NAVICAST_DB_PASSWORD (required)
sudo -u postgres psql -c "CREATE DATABASE ais_project;"
sudo -u postgres psql -d ais_project -f schema.sql
mkdir -p logs
./start_navicast.sh
```

| Env var | Required | Default | Purpose |
|---|---|---|---|
| `NAVICAST_DB_PASSWORD` | yes | — | Postgres password (`config.get_db_config` raises without it) |
| `NAVICAST_DB_NAME` / `NAVICAST_DB_USER` / `NAVICAST_DB_HOST` / `NAVICAST_DB_PORT` | no | `ais_project` / `postgres` / `localhost` / `5432` | DB connection |
| `NAVICAST_CORS_ORIGINS` | no | `http://localhost:3000` | Comma-separated API CORS origins |
| `NAVICAST_MODEL_PATH` | no | `vessel_prediction_model.pkl` | ML model file; missing → dead-reckoning fallback |
| `PORT` | no | `8000` | API listen port (`api_server.py` reads it; also compose host mapping) |

Notebook extras: `pip install -r requirements-notebook.txt`. Dev tools: `pip install -r requirements-dev.txt`.

## API

| Endpoint | Description |
|---|---|
| `GET /vessels` | Latest position + prediction per vessel. Params: `mmsi`, `from_time`, `to_time`, `limit` (default 100) |
| `GET /vessels/download` | Same data as JSON/CSV export |
| `GET /vessels/{id}` | Detail for one vessel (MMSI) |
| `GET /health` | Health check |

## Data

- **Volume**: ~50-200 messages/minute (~500 bytes each) from the Digitraffic AIS feed.
- **Tables**: `raw_ais_data` (PK `vessel_id, timestamp`), `predictions` (one row per vessel, PK `vessel_id`; see `docs/data_architecture.md`).
- **Retention**: raw data 24h by default; predictions expire 1h after `prediction_made_at` (`PREDICTION_TTL_HOURS = 1`).
- Stale map markers: the frontend flags vessels whose AIS timestamp is older than the display threshold.

## ML model

Random Forest predicts positions 30 min ahead (median error ~11 m on test data); see `ML_Model.ipynb`. The service runs without the model file via dead reckoning.

## Docs

- `docs/data_architecture.md` — components, schema, TTL
- `docs/data_management_plan.md` — collection, retention, ethics
- `ML_Model.ipynb` — model analysis

## License

MIT — see `LICENSE`. AIS data: Finnish Transport Agency (Digitraffic).
