import math
import psycopg2
import logging
from logging.handlers import RotatingFileHandler
import time
import schedule
from datetime import datetime, timedelta, timezone
from config import BOUNDS, ensure_log_dir, get_db_config

# Create logs directory if it doesn't exist
LOG_DIR = ensure_log_dir()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(str(LOG_DIR / 'prediction_service.log'), maxBytes=10485760, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
PREDICTION_HORIZON_SECONDS = 1800
PREDICTION_CADENCE_MINUTES = 5
AIS_RECENCY_MINUTES = 30
PREDICTION_TTL_HOURS = 1

DB_CONFIG = get_db_config()

# Calculate vessel position prediction
def calculate_position_prediction(lat, lon, sog, cog, time_diff):
    """Calculate predicted position using dead reckoning"""
    # Convert speed from knots to meters per second
    speed_mps = sog * 0.51444
    
    # Calculate position change using basic trigonometry
    # Approximately 111,111 meters per degree of latitude
    delta_lat = (speed_mps * math.cos(math.radians(cog)) * time_diff) / 111111
    
    # Adjust longitude calculation for latitude (converging meridians)
    cos_lat = math.cos(math.radians(lat))
    if abs(cos_lat) < 0.01:  # Avoid division by very small numbers near poles
        cos_lat = 0.01 if cos_lat >= 0 else -0.01
    
    delta_lon = (speed_mps * math.sin(math.radians(cog)) * time_diff) / (111111 * cos_lat)
    
    return delta_lat, delta_lon

def make_predictions():
    """Project latest observations by constant speed and course for 30 minutes."""
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        # Extract text: malformed historical motion must not abort the whole SELECT.
        cur.execute("""
            SELECT DISTINCT ON (vessel_id)
                vessel_id, latitude, longitude,
                raw_json -> 'properties' ->> 'sog',
                raw_json -> 'properties' ->> 'cog',
                raw_json -> 'properties' ->> 'heading', timestamp
            FROM raw_ais_data
            WHERE timestamp > NOW() - (%s * INTERVAL '1 minute')
            ORDER BY vessel_id, timestamp DESC
        """, (AIS_RECENCY_MINUTES,))
        predictions_count = 0
        for vessel_id, lat, lon, sog, cog, heading, timestamp in cur.fetchall():
            try:
                if any(isinstance(value, bool) for value in (lat, lon, sog, cog)):
                    raise ValueError("Invalid motion values")
                lat, lon, sog, cog = map(float, (lat, lon, sog, cog))
                if (not all(math.isfinite(value) for value in (lat, lon, sog, cog))
                        or not -90 <= lat <= 90 or not -180 <= lon <= 180
                        or not 0.5 <= sog < 102.3 or not 0 <= cog < 360
                        or not isinstance(timestamp, datetime)):
                    raise ValueError("Unavailable or invalid motion")
                delta_lat, delta_lon = calculate_position_prediction(
                    lat, lon, sog, cog, PREDICTION_HORIZON_SECONDS)
                predicted_lat, predicted_lon = lat + delta_lat, lon + delta_lon
                if (abs(delta_lat) > 0.5 or abs(delta_lon) > 0.5
                        or not BOUNDS["lat_min"] <= predicted_lat <= BOUNDS["lat_max"]
                        or not BOUNDS["lon_min"] <= predicted_lon <= BOUNDS["lon_max"]):
                    raise ValueError("Projection outside configured region or displacement limit")
                prediction_for = timestamp + timedelta(seconds=PREDICTION_HORIZON_SECONDS)
            except (TypeError, ValueError, OverflowError) as exc:
                logger.warning("Skipping projection for vessel %s: %s", vessel_id, exc)
                continue

            cur.execute("SAVEPOINT prediction_row")
            try:
                cur.execute("""
                    INSERT INTO predictions
                        (vessel_id, predicted_latitude, predicted_longitude,
                         prediction_for_timestamp, prediction_made_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (vessel_id) DO UPDATE SET
                        predicted_latitude = EXCLUDED.predicted_latitude,
                        predicted_longitude = EXCLUDED.predicted_longitude,
                        prediction_for_timestamp = EXCLUDED.prediction_for_timestamp,
                        prediction_made_at = EXCLUDED.prediction_made_at
                """, (vessel_id, predicted_lat, predicted_lon, prediction_for, datetime.now(timezone.utc)))
                predictions_count += 1
            except psycopg2.Error as exc:
                cur.execute("ROLLBACK TO SAVEPOINT prediction_row")
                logger.warning("Skipping rejected projection for vessel %s: %s", vessel_id, exc)
            finally:
                cur.execute("RELEASE SAVEPOINT prediction_row")

        cur.execute("DELETE FROM predictions WHERE prediction_made_at < NOW() - (%s * INTERVAL '1 hour')",
                    (PREDICTION_TTL_HOURS,))
        conn.commit()
        logger.info("Committed %s constant-course projections", predictions_count)
    except Exception as exc:
        logger.error("Prediction cycle failed: %s", exc)
        if conn:
            try:
                conn.rollback()
            except psycopg2.Error:
                logger.warning("Could not roll back a failed database connection")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def main():
    """Main function to run the prediction service"""
    try:
        # Make predictions immediately at startup
        make_predictions()
        
        # Schedule the periodic prediction task (every 5 minutes)
        schedule.every(PREDICTION_CADENCE_MINUTES).minutes.do(make_predictions)
        
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
