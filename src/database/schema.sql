-- Raw AIS data
CREATE TABLE raw_ais_data (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    payload JSONB
);

-- Enriched AIS data
CREATE TABLE enriched_ais_data (
    id SERIAL PRIMARY KEY,
    vessel_id INT,
    latitude FLOAT,
    longitude FLOAT,
    speed FLOAT,
    predicted_lat FLOAT,
    predicted_lon FLOAT
);