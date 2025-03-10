import psycopg2
import pandas as pd
import joblib
from datetime import datetime, timedelta
import schedule
import time
import logging
import numpy as np

logging.basicConfig(filename='prediction_service.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

model = joblib.load('vessel_prediction_model.pkl')

def make_predictions():
    try:
        conn = psycopg2.connect(
            dbname="ais_project",
            user="postgres",
            password="120705imad",
            host="localhost"
        )
        cur = conn.cursor()

        query = """
        SELECT 
            vessel_id, 
            latitude, 
            longitude, 
            (raw_json -> 'properties' ->> 'sog')::float AS sog,
            (raw_json -> 'properties' ->> 'cog')::float AS cog,
            COALESCE((raw_json -> 'properties' ->> 'heading')::float, 0) AS heading,
            timestamp
        FROM raw_ais_data
        WHERE (vessel_id, timestamp) IN (
            SELECT vessel_id, MAX(timestamp)
            FROM raw_ais_data
            WHERE timestamp > NOW() - INTERVAL '15 minutes'
            GROUP BY vessel_id
        )
        """
        cur.execute(query)
        latest_data = cur.fetchall()

        if not latest_data:
            logging.info("No recent AIS data to process for predictions")
            print(f"{datetime.now()}: No recent AIS data to process")
            return

        for row in latest_data:
            vessel_id, lat, lon, sog, cog, heading, timestamp = row
            
            # Skip vessels that aren't moving
            if sog is not None and sog < 0.5:
                logging.info(f"Skipping vessel {vessel_id} with low speed ({sog} knots)")
                continue
                
            input_data = pd.DataFrame({
                'latitude': [lat],
                'longitude': [lon],
                'sog': [sog if sog is not None else 0],
                'cog': [cog if cog is not None else 0],
                'heading': [heading if heading is not None else 0],
                'time_diff': [300]
            })
            
            try:
                delta_lat, delta_lon = model.predict(input_data)[0]
                logging.info(f"Model prediction for vessel {vessel_id}: delta_lat={delta_lat:.6f}, delta_lon={delta_lon:.6f}")
            except Exception as e:
                logging.error(f"Model prediction failed for vessel {vessel_id}: {e}")
                # Fallback: Calculate deltas based on sog and cog
                time_diff = 300  # 5 minutes in seconds
                speed_mps = (sog if sog is not None else 0) * 0.51444  # knots to m/s
                
                # Ensure cog is valid
                cog_val = cog if cog is not None else 0
                if cog_val < 0 or cog_val > 360:
                    cog_val = 0
                    
                delta_lat = (speed_mps * np.cos(np.radians(cog_val)) * time_diff) / 111111  # meters to degrees latitude
                delta_lon = (speed_mps * np.sin(np.radians(cog_val)) * time_diff) / (111111 * np.cos(np.radians(lat)))  # meters to degrees longitude
                logging.info(f"Fallback prediction for vessel {vessel_id}: delta_lat={delta_lat:.6f}, delta_lon={delta_lon:.6f}")

            predicted_lat = lat + delta_lat
            predicted_lon = lon + delta_lon

            # More lenient validation for the Baltic Sea region
            if (abs(delta_lat) > 2.0 or abs(delta_lon) > 2.0 or
                predicted_lat < 50 or predicted_lat > 70 or
                predicted_lon < 10 or predicted_lon > 30):
                logging.warning(f"Invalid prediction for vessel {vessel_id}: "
                                f"delta_lat={delta_lat:.4f}, delta_lon={delta_lon:.4f}, "
                                f"predicted_lat={predicted_lat:.4f}, predicted_lon={predicted_lon:.4f}")
                continue

            prediction_for = timestamp + timedelta(seconds=300)
            prediction_made = datetime.now()

            update_query = """
            INSERT INTO predictions (vessel_id, predicted_latitude, predicted_longitude, prediction_for_timestamp, prediction_made_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (vessel_id) DO UPDATE SET
                predicted_latitude = EXCLUDED.predicted_latitude,
                predicted_longitude = EXCLUDED.predicted_longitude,
                prediction_for_timestamp = EXCLUDED.prediction_for_timestamp,
                prediction_made_at = EXCLUDED.prediction_made_at
            """
            cur.execute(update_query, (vessel_id, predicted_lat, predicted_lon, prediction_for, prediction_made))
            logging.info(f"Prediction stored for vessel {vessel_id}: predicted_lat={predicted_lat:.4f}, predicted_lon={predicted_lon:.4f}")

        conn.commit()
        print(f"{datetime.now()}: Updated predictions for {len(latest_data)} vessels")
    except Exception as e:
        logging.error(f"Error in make_predictions: {e}")
    finally:
        if 'conn' in locals() and conn is not None:
            if 'cur' in locals() and cur is not None:
                cur.close()
            conn.close()

# Run once immediately at startup
make_predictions()

# Then schedule regular updates
schedule.every(1).minutes.do(make_predictions)

while True:
    schedule.run_pending()
    time.sleep(1)