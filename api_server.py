from fastapi import FastAPI, HTTPException
import psycopg2
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import logging

app = FastAPI()

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up logging
logging.basicConfig(filename='api_server.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

@app.get("/vessels")
def get_vessels():
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
            a.vessel_id, 
            a.latitude AS current_latitude, 
            a.longitude AS current_longitude, 
            a.timestamp AS current_timestamp,
            (a.raw_json -> 'properties' ->> 'sog')::float AS sog,
            (a.raw_json -> 'properties' ->> 'cog')::float AS cog,
            (a.raw_json -> 'properties' ->> 'posAcc')::boolean AS pos_acc,
            p.predicted_latitude, 
            p.predicted_longitude, 
            p.prediction_for_timestamp, 
            p.prediction_made_at
        FROM (
            SELECT 
                vessel_id, 
                latitude, 
                longitude, 
                timestamp,
                raw_json
            FROM raw_ais_data
            WHERE (vessel_id, timestamp) IN (
                SELECT vessel_id, MAX(timestamp)
                FROM raw_ais_data
                GROUP BY vessel_id
            )
        ) a
        LEFT JOIN predictions p ON a.vessel_id = p.vessel_id
        ORDER BY a.timestamp DESC
        """
        cur.execute(query)
        vessels = cur.fetchall()
        
        # Prepare response
        response = []
        for row in vessels:
            vessel_id, lat, lon, timestamp, sog, cog, pos_acc, pred_lat, pred_lon, pred_for, pred_made = row
            
            # Basic sanity checks for Baltic Sea region
            valid_prediction = True
            if pred_lat is not None and pred_lon is not None:
                if (pred_lat < 50 or pred_lat > 70 or 
                    pred_lon < 10 or pred_lon > 30):
                    valid_prediction = False
                    logging.warning(f"Invalid prediction for vessel {vessel_id}: "
                                   f"current=({lat:.4f}, {lon:.4f}), "
                                   f"predicted=({pred_lat:.4f}, {pred_lon:.4f})")

            vessel_data = {
                "vessel_id": vessel_id,
                "current_latitude": lat,
                "current_longitude": lon,
                "current_timestamp": timestamp.isoformat(),
                "sog": sog,
                "cog": cog,
                "pos_acc": pos_acc
            }
            
            if valid_prediction and pred_lat is not None and pred_lon is not None:
                vessel_data.update({
                    "predicted_latitude": pred_lat,
                    "predicted_longitude": pred_lon,
                    "prediction_for_timestamp": pred_for.isoformat() if pred_for else None,
                    "prediction_made_at": pred_made.isoformat() if pred_made else None
                })
                logging.info(f"Sending valid prediction for vessel {vessel_id}")
            else:
                vessel_data.update({
                    "predicted_latitude": None,
                    "predicted_longitude": None,
                    "prediction_for_timestamp": None,
                    "prediction_made_at": None
                })

            response.append(vessel_data)

        logging.info(f"Returning {len(response)} vessels, {sum(1 for v in response if v['predicted_latitude'] is not None)} with predictions")
        return response
    except Exception as e:
        logging.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    import uvicorn
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
    uvicorn.run(app, host="0.0.0.0", port=8000)