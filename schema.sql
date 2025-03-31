DROP TABLE IF EXISTS raw_ais_data CASCADE;
DROP TABLE IF EXISTS predictions CASCADE;

CREATE TABLE raw_ais_data (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER,
    latitude FLOAT,
    longitude FLOAT,
    timestamp TIMESTAMP,
    raw_json JSONB
);

CREATE TABLE predictions (
    vessel_id BIGINT PRIMARY KEY,
    predicted_latitude DOUBLE PRECISION,
    predicted_longitude DOUBLE PRECISION,
    prediction_for_timestamp TIMESTAMP,
    prediction_made_at TIMESTAMP
); 