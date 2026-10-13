-- NAVICAST sample seed data (reviewer boot path: /vessels returns 200 without MQTT).
-- Load after schema.sql. Timestamps are relative to NOW() so seed data is fresh.
-- raw_json mirrors the ingest path (mqtt_client.py stores the whole vessel object):
-- top-level mmsi/lat/lon plus a "properties" object (sog/cog/heading/posAcc/navStat/shipType),
-- which is the shape api_server.py reads (raw_json -> 'properties' ->> ...).

INSERT INTO raw_ais_data (vessel_id, latitude, longitude, timestamp, raw_json) VALUES
(230001000, 59.92, 24.75, NOW() - INTERVAL '5 minutes',
 '{"mmsi": "230001000", "lat": 59.92, "lon": 24.75, "properties": {"sog": 12.5, "cog": 95.0, "heading": 96, "posAcc": true, "navStat": 0, "shipType": 70}}'),
(211234000, 55.10, 18.20, NOW() - INTERVAL '8 minutes',
 '{"mmsi": "211234000", "lat": 55.10, "lon": 18.20, "properties": {"sog": 8.0, "cog": 45.0, "heading": 44, "posAcc": true, "navStat": 0, "shipType": 80}}'),
(265111000, 58.55, 17.05, NOW() - INTERVAL '12 minutes',
 '{"mmsi": "265111000", "lat": 58.55, "lon": 17.05, "properties": {"sog": 0.0, "cog": 0.0, "heading": 180, "posAcc": true, "navStat": 1, "shipType": 60}}'),
(219876000, 56.30, 20.40, NOW() - INTERVAL '20 minutes',
 '{"mmsi": "219876000", "lat": 56.30, "lon": 20.40, "properties": {"sog": 15.2, "cog": 270.0, "heading": 271, "posAcc": false, "navStat": 0, "shipType": 30}}');

INSERT INTO predictions (vessel_id, predicted_latitude, predicted_longitude, prediction_for_timestamp, prediction_made_at) VALUES
(230001000, 59.93, 24.95, NOW() + INTERVAL '30 minutes', NOW() - INTERVAL '5 minutes'),
(211234000, 55.15, 18.28, NOW() + INTERVAL '30 minutes', NOW() - INTERVAL '8 minutes');
