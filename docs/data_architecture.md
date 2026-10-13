# Data architecture

NaviCast has a database-free demo path and a PostgreSQL-backed live path. Both use the same FastAPI routes and Leaflet page.

## Demo

With `NAVICAST_MODE=demo`, the API calls `demo_data.sample_rows()` for each vessel request. It returns four explicitly synthetic records with timestamps relative to the current UTC time. Moving vessels receive 30-minute straight-line estimates calculated from speed and course. The API reports the mode and method at `/meta`, and marks each record with `data_source: synthetic`. No database, MQTT client, or model file is used.

## Live data flow

```text
Digitraffic MQTT → mqtt_client.py → PostgreSQL → prediction_service.py
                                              ↓
                                      api_server.py → Leaflet page
```

The MQTT client stores vessel positions and the original message in `raw_ais_data`. The prediction service reads recent positions and writes 30-minute dead-reckoning estimates to `predictions`. The API returns the newest position and any unexpired prediction. The served application does not load a trained model.

## Storage

- `raw_ais_data` stores `vessel_id`, latitude, longitude, a timezone-aware timestamp, and the source message as JSONB. Its primary key is `(vessel_id, timestamp)`.
- `predictions` stores one current row per vessel, including predicted coordinates, the target time, and the time the estimate was made. `vessel_id` is the primary key; `(vessel_id, prediction_for_timestamp)` is also unique.
- Live ingestion removes raw rows older than 24 hours. The prediction service removes predictions older than one hour.
- `schema.sql` creates missing tables and indexes without deleting existing records. It does not migrate incompatible schemas.

## API and map

- `GET /vessels` returns the latest vessel data with optional MMSI, time-range, and result-limit filters.
- `GET /vessels/{vessel_id}` returns one vessel.
- `GET /vessels/download?format=json|csv` exports data.
- `GET /meta` reports demo/live mode and the prediction method.
- `GET /health` reports API health and checks PostgreSQL in live mode.

The page polls `/vessels` and draws current positions and estimates. It loads Leaflet assets and map tiles from external services.

## Access boundary

The live API has no authentication. Keep it on a trusted network. AIS broadcasts are public, but vessel identifiers, positions, and movement history can still be sensitive in context.

The notebook and figures in `docs/ML_Model_docs/` are historical experiments. Their metrics have not been validated for the current live pipeline and are not used by the API.
