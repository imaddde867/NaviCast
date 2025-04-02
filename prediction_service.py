import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
import joblib
import logging
from logging.handlers import RotatingFileHandler
import time
import schedule
import traceback
import os
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/prediction_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
MODEL_PATH = 'vessel_prediction_model.pkl'
PREDICTION_INTERVAL = 1800  # 30 minutes in seconds

# Database configuration
DB_CONFIG = {
    'dbname': 'ais_project',
    'user': 'postgres',
    'password': '120705imad',
    'host': 'localhost'
}

# Use DATABASE_URL environment variable if available (for Render.com)
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    logger.info(f"Using DATABASE_URL from environment")
    # Parse the connection string
    parsed_url = urllib.parse.urlparse(DATABASE_URL)
    DB_CONFIG = {
        "dbname": parsed_url.path[1:],
        "user": parsed_url.username,
        "password": parsed_url.password,
        "host": parsed_url.hostname,
        "port": parsed_url.port or 5432
    }

# Baltic Sea boundaries (for validation)
LAT_MIN = 53
LAT_MAX = 66
LON_MIN = 9
LON_MAX = 30

# Load prediction model
def load_model():
    """Load the vessel prediction model"""
    try:
        logger.info("Loading prediction model...")
        model = joblib.load(MODEL_PATH)
        logger.info("Prediction model loaded successfully")
        return model
    except Exception as e:
        logger.error(f"Failed to load prediction model: {e}")
        raise

# Calculate vessel position prediction
def calculate_position_prediction(lat, lon, sog, cog, time_diff):
    """Calculate predicted position using dead reckoning"""
    # Convert speed from knots to meters per second
    speed_mps = sog * 0.51444
    
    # Calculate position change using basic trigonometry
    # Approximately 111,111 meters per degree of latitude
    delta_lat = (speed_mps * np.cos(np.radians(cog)) * time_diff) / 111111
    
    # Adjust longitude calculation for latitude (converging meridians)
    cos_lat = np.cos(np.radians(lat))
    if abs(cos_lat) < 0.01:  # Avoid division by very small numbers near poles
        cos_lat = 0.01 if cos_lat >= 0 else -0.01
    
    delta_lon = (speed_mps * np.sin(np.radians(cog)) * time_diff) / (111111 * cos_lat)
    
    return delta_lat, delta_lon

def make_predictions():
    """Retrieve latest vessel data and generate predictions"""
    logger.info("Starting prediction cycle...")
    start_time = time.time()
    
    conn = None
    cur = None
    try:
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Get the latest vessel data
        query = """
        SELECT 
            vessel_id, 
            latitude, 
            longitude, 
            COALESCE((raw_json -> 'properties' ->> 'sog')::float, 0) AS sog,
            COALESCE((raw_json -> 'properties' ->> 'cog')::float, 0) AS cog,
            COALESCE((raw_json -> 'properties' ->> 'heading')::float, 0) AS heading,
            timestamp
        FROM raw_ais_data
        WHERE (vessel_id, timestamp) IN (
            SELECT vessel_id, MAX(timestamp)
            FROM raw_ais_data
            WHERE timestamp > NOW() - INTERVAL '30 minutes'
            GROUP BY vessel_id
        )
        """
        cur.execute(query)
        latest_data = cur.fetchall()

        if not latest_data:
            logger.info("No recent AIS data to process for predictions")
            return

        logger.info(f"Processing predictions for {len(latest_data)} vessels")
        predictions_count = 0
        skipped_count = 0

        # Process each vessel
        for vessel_data in latest_data:
            vessel_id, lat, lon, sog, cog, heading, timestamp = vessel_data
            
            # Skip vessels with invalid position data
            if lat is None or lon is None:
                logger.warning(f"Skipping vessel {vessel_id} with invalid position")
                skipped_count += 1
                continue
                
            # Skip stationary vessels
            if sog is None or sog < 0.5:
                logger.info(f"Skipping vessel {vessel_id} with low speed ({sog} knots)")
                skipped_count += 1
                continue
            
            # Validate and normalize input values
            sog_val = max(0.0, min(50.0, float(sog) if sog is not None else 0.0))
            cog_val = max(0.0, min(360.0, float(cog) if cog is not None and 0 <= cog <= 360 else 0.0))
            heading_val = max(0.0, min(360.0, float(heading) if heading is not None and 0 <= heading <= 360 else cog_val))
            
            # Prepare input data for the model
            try:
                input_data = pd.DataFrame({
                    'latitude': [float(lat)],
                    'longitude': [float(lon)],
                    'sog': [sog_val],
                    'cog': [cog_val],
                    'heading': [heading_val],
                    'time_diff': [PREDICTION_INTERVAL]
                })
                
                # Try to use the model for prediction
                try:
                    delta_lat, delta_lon = model.predict(input_data)[0]
                    logger.debug(f"Model prediction for vessel {vessel_id}: delta_lat={delta_lat:.6f}, delta_lon={delta_lon:.6f}")
                except Exception as e:
                    logger.warning(f"Model prediction failed for vessel {vessel_id}: {e}")
                    # Fallback to dead reckoning
                    delta_lat, delta_lon = calculate_position_prediction(lat, lon, sog_val, cog_val, PREDICTION_INTERVAL)
                    logger.debug(f"Fallback prediction for vessel {vessel_id}: delta_lat={delta_lat:.6f}, delta_lon={delta_lon:.6f}")

                # Calculate predicted position
                predicted_lat = lat + delta_lat
                predicted_lon = lon + delta_lon

                # Validate prediction is within reasonable bounds
                if (abs(delta_lat) > 0.5 or abs(delta_lon) > 0.5 or  # Maximum ~30nm in 30 minutes
                    predicted_lat < LAT_MIN or predicted_lat > LAT_MAX or
                    predicted_lon < LON_MIN or predicted_lon > LON_MAX):
                    logger.warning(f"Invalid prediction for vessel {vessel_id}: "
                                f"predicted_lat={predicted_lat:.4f}, predicted_lon={predicted_lon:.4f}")
                    skipped_count += 1
                    continue

                # Calculate timestamps
                prediction_for = timestamp + timedelta(seconds=PREDICTION_INTERVAL)
                prediction_made = datetime.now()

                # Store the prediction
                cur.execute("""
                    INSERT INTO predictions 
                        (vessel_id, predicted_latitude, predicted_longitude, prediction_for_timestamp, prediction_made_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT ON CONSTRAINT predictions_pkey DO UPDATE SET
                        predicted_latitude = EXCLUDED.predicted_latitude,
                        predicted_longitude = EXCLUDED.predicted_longitude,
                        prediction_for_timestamp = EXCLUDED.prediction_for_timestamp,
                        prediction_made_at = EXCLUDED.prediction_made_at
                """, (vessel_id, predicted_lat, predicted_lon, prediction_for, prediction_made))
                
                predictions_count += 1
                
            except Exception as e:
                logger.error(f"Error processing prediction for vessel {vessel_id}: {e}")
                skipped_count += 1

        # Commit all changes
        conn.commit()
        
        # Clean up old predictions
        try:
            cur.execute("DELETE FROM predictions WHERE prediction_made_at < NOW() - INTERVAL '1 hour'")
            conn.commit()
            logger.info("Cleaned up old predictions")
        except Exception as e:
            logger.warning(f"Failed to clean up old predictions: {e}")
            
        duration = time.time() - start_time
        logger.info(f"Prediction cycle completed in {duration:.2f}s. Created {predictions_count} predictions, skipped {skipped_count} vessels.")
    
    except Exception as e:
        logger.error(f"Error in make_predictions: {e}")
        if conn:
            conn.rollback()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def main():
    """Main function to run the prediction service"""
    try:
        # Load the model at startup
        global model
        model = load_model()
        
        # Make predictions immediately at startup
        make_predictions()
        
        # Schedule the periodic prediction task (every 5 minutes)
        schedule.every(5).minutes.do(make_predictions)
        
        logger.info("Prediction service started. Making predictions every 5 minutes...")
        
        # Run the scheduler in a loop
        while True:
            schedule.run_pending()
            time.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("Prediction service stopped by user")
    except Exception as e:
        logger.error(f"Prediction service failed: {e}")
        raise

if __name__ == "__main__":
    main()