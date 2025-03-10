import psycopg2
import pandas as pd
import joblib
from datetime import datetime, timedelta
import schedule
import time
import numpy as np

# Load the model
model = joblib.load('vessel_prediction_model.pkl')

def make_predictions():
    conn = psycopg2.connect(
        dbname="ais_project",
        user="postgres",
        password="120705imad",
        host="localhost"
    )
    cur = conn.cursor()

    # Fetch latest AIS data per vessel
    query = """
    SELECT 
        vessel_id, 
        latitude, 
        longitude, 
        (raw_json -> 'properties' ->> 'sog')::float AS sog,
        (raw_json -> 'properties' ->> 'cog')::float AS cog,
        COALESCE((raw_json -> 'properties' ->> 'heading')::float, 0) AS heading,
        (raw_json -> 'properties' ->> 'navStat')::int AS nav_stat,
        (raw_json -> 'properties' ->> 'rot')::float AS rot,
        (raw_json -> 'properties' ->> 'posAcc')::boolean AS pos_acc,
        (raw_json -> 'properties' ->> 'raim')::boolean AS raim,
        timestamp
    FROM raw_ais_data
    WHERE (vessel_id, timestamp) IN (
        SELECT vessel_id, MAX(timestamp)
        FROM raw_ais_data
        GROUP BY vessel_id
    )
    """
    cur.execute(query)
    latest_data = cur.fetchall()

    for row in latest_data:
        vessel_id, lat, lon, sog, cog, heading, nav_stat, rot, pos_acc, raim, timestamp = row
        
        # Calculate delta values based on speed and course (simplified version)
        time_diff = 300  # 5 minutes in seconds
        delta_lat = (sog * 0.51444 * np.cos(np.radians(cog)) * time_diff) / 111_111 if sog and cog else 0
        delta_lon = (sog * 0.51444 * np.sin(np.radians(cog)) * time_diff) / (111_111 * np.cos(np.radians(lat))) if sog and cog and lat else 0
        
        # Convert boolean to int
        pos_acc_int = 1 if pos_acc else 0
        raim_int = 1 if raim else 0
        
        # Prepare input with all required features
        input_data = pd.DataFrame({
            'latitude': [lat],
            'longitude': [lon],
            'sog': [sog if sog is not None else 0],
            'cog': [cog if cog is not None else 0],
            'navStat': [nav_stat if nav_stat is not None else 0],
            'rot': [rot if rot is not None else 0],
            'posAcc': [pos_acc_int],
            'raim': [raim_int],
            'heading': [heading if heading is not None else 0],
            'time_diff': [time_diff],
            'delta_lat': [delta_lat],
            'delta_lon': [delta_lon],
            'is_water': [1]  # Assume vessel is on water
        })
        
        # Predict deltas
        delta_lat, delta_lon = model.predict(input_data)[0]
        predicted_lat = lat + delta_lat
        predicted_lon = lon + delta_lon

        # Update predictions table
        prediction_for = timestamp + timedelta(seconds=300)
        prediction_made = datetime.now()

        # Update predictions table
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

    conn.commit()
    cur.close()
    conn.close()
    print(f"{datetime.now()}: Updated predictions")

# Run every minute
schedule.every(1).minutes.do(make_predictions)

while True:
    schedule.run_pending()
    time.sleep(1)