-- NAVICAST Database Schema
-- PostgreSQL 13.0+

-- Create database
-- Run this command separately first: 
-- CREATE DATABASE ais_project;

-- Connect to the database
\c ais_project;

-- Drop tables if they exist (for clean setup)
DROP TABLE IF EXISTS predictions;
DROP TABLE IF EXISTS raw_ais_data;

-- Create raw AIS data table
CREATE TABLE raw_ais_data (
    vessel_id INTEGER NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    raw_json JSONB,
    PRIMARY KEY (vessel_id, timestamp)
);

-- Create predictions table
CREATE TABLE predictions (
    vessel_id INTEGER NOT NULL,
    predicted_latitude DOUBLE PRECISION NOT NULL,
    predicted_longitude DOUBLE PRECISION NOT NULL,
    prediction_for_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    prediction_made_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (vessel_id),
    CONSTRAINT unique_vessel_prediction UNIQUE (vessel_id, prediction_for_timestamp)
);

-- Create indices for faster queries
CREATE INDEX idx_raw_ais_data_timestamp ON raw_ais_data(timestamp);
CREATE INDEX idx_raw_ais_data_vessel_id ON raw_ais_data(vessel_id);
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
    DELETE FROM raw_ais_data 
    WHERE timestamp < cutoff_date;
    
    RAISE NOTICE 'Deleted vessel and prediction data older than %', cutoff_date;
END;
$$ LANGUAGE plpgsql;

-- Create a role for the application (if needed)
-- CREATE ROLE navicast WITH LOGIN PASSWORD 'your_secure_password';
-- GRANT ALL PRIVILEGES ON DATABASE ais_project TO navicast;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO navicast;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO navicast;