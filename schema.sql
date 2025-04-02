-- NAVICAST Database Schema
-- PostgreSQL 13.0+

-- Create database
-- Run this command separately first: 
-- CREATE DATABASE ais_data;

-- Connect to the database
\c ais_data;

-- Drop tables if they exist (for clean setup)
DROP TABLE IF EXISTS predictions;
DROP TABLE IF EXISTS vessels;

-- Create vessels table
CREATE TABLE vessels (
    vessel_id INTEGER PRIMARY KEY,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    sog DOUBLE PRECISION,
    cog DOUBLE PRECISION,
    heading INTEGER,
    nav_stat INTEGER,
    pos_acc BOOLEAN,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    raw_json JSONB
);

-- Create predictions table
CREATE TABLE predictions (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER REFERENCES vessels(vessel_id),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    prediction_for_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    prediction_made_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT unique_vessel_prediction UNIQUE (vessel_id, prediction_for_timestamp)
);

-- Create indices for faster queries
CREATE INDEX idx_vessels_timestamp ON vessels(timestamp);
CREATE INDEX idx_predictions_vessel_id ON predictions(vessel_id);
CREATE INDEX idx_predictions_timestamp ON predictions(prediction_for_timestamp);

-- Create a function to clean up old data (optional)
CREATE OR REPLACE FUNCTION cleanup_old_data(days_to_keep INTEGER)
RETURNS void AS $$
DECLARE
    cutoff_date TIMESTAMP WITH TIME ZONE;
BEGIN
    cutoff_date := NOW() - (days_to_keep * INTERVAL '1 day');
    
    -- Delete old predictions
    DELETE FROM predictions 
    WHERE prediction_made_at < cutoff_date;
    
    -- Delete old vessel data
    DELETE FROM vessels 
    WHERE timestamp < cutoff_date;
    
    RAISE NOTICE 'Deleted vessel and prediction data older than %', cutoff_date;
END;
$$ LANGUAGE plpgsql;

-- Create a role for the application (if needed)
-- CREATE ROLE navicast WITH LOGIN PASSWORD 'your_secure_password';
-- GRANT ALL PRIVILEGES ON DATABASE ais_data TO navicast;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO navicast;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO navicast;

-- Sample usage of cleanup function (commented out)
-- SELECT cleanup_old_data(30); -- Keep 30 days of data 