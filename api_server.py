from fastapi import FastAPI, HTTPException, Depends, Query
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import logging
from logging.handlers import RotatingFileHandler
import pandas as pd
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import os
from fastapi.responses import JSONResponse
import uvicorn

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('logs/api_server.log', maxBytes=10485760, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("navicast.api")

# Constants
# Default database configuration
DB_CONFIG = {
    "dbname": "ais_project",
    "user": "postgres",
    "password": "120705imad",
    "host": "localhost"
}

# Map AIS navigation status codes to human-readable descriptions
NAV_STATUS_MAP = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted maneuverability",
    4: "Constrained by draft",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    9: "Reserved",
    10: "Reserved",
    11: "Reserved",
    12: "Reserved",
    13: "Reserved",
    14: "AIS-SART active",
    15: "Not defined"
}

# Map ship type codes to descriptions
SHIP_TYPE_MAP = {
    0: "Not available",
    20: "Wing in ground",
    30: "Fishing",
    31: "Tug",
    32: "Tug",
    33: "Dredger",
    34: "Dive vessel",
    35: "Military",
    36: "Sailing vessel",
    37: "Pleasure craft",
    40: "High-speed craft",
    50: "Pilot vessel",
    51: "Search and rescue",
    52: "Tug",
    53: "Port tender",
    54: "Anti-pollution",
    55: "Law enforcement",
    60: "Passenger",
    70: "Cargo",
    71: "Cargo - hazard A",
    72: "Cargo - hazard B",
    73: "Cargo - hazard C",
    74: "Cargo - hazard D",
    80: "Tanker",
    91: "Unknown",
    99: "Other"
}

# Valid boundaries for the Baltic Sea region
BOUNDS = {
    "lat_min": 50.0,
    "lat_max": 70.0,
    "lon_min": 10.0,
    "lon_max": 30.0
}

app = FastAPI(
    title="NAVICAST API",
    description="API for the NAVICAST vessel tracking and prediction system",
    version="1.0.0"
)

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load MMSI to country mapping
mmsi_country_map = {}
try:
    mmsi_country_map = pd.read_csv('mid_to_country.csv').set_index('MID')['Country'].to_dict()
    logger.info(f"Loaded {len(mmsi_country_map)} MMSI country mappings")
except Exception as e:
    logger.warning(f"Could not load MMSI country mappings: {e}")

def get_db_connection():
    """Creates and returns a database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Database connection failed: {str(e)}"
        )

def get_country_from_mmsi(mmsi: int) -> Optional[str]:
    """Maps MMSI to country based on Maritime Identification Digits (MID)"""
    if mmsi and isinstance(mmsi, int):
        try:
            mmsi_prefix = str(mmsi)[:3]
            return mmsi_country_map.get(int(mmsi_prefix))
        except (ValueError, TypeError):
            pass
    return None

def is_valid_prediction(lat: float, lon: float) -> bool:
    """Validates if a prediction falls within the defined bounds"""
    if lat is None or lon is None:
        return False
        
    return (BOUNDS["lat_min"] <= lat <= BOUNDS["lat_max"] and 
            BOUNDS["lon_min"] <= lon <= BOUNDS["lon_max"])

def get_vessel_type(raw_json: Dict) -> tuple:
    """Extracts and maps vessel type from AIS data"""
    vessel_type = "Unknown"
    vessel_type_code = None
    
    if not raw_json or not isinstance(raw_json, dict):
        return vessel_type, vessel_type_code
        
    props = raw_json.get('properties', {})
    vessel_type_code = props.get('shipType')
    
    if vessel_type_code is not None:
        # First try exact match
        if vessel_type_code in SHIP_TYPE_MAP:
            vessel_type = SHIP_TYPE_MAP[vessel_type_code]
        else:
            # Try category match (first digit * 10)
            tens = (vessel_type_code // 10) * 10
            if tens in SHIP_TYPE_MAP:
                vessel_type = SHIP_TYPE_MAP[tens]
    
    return vessel_type, vessel_type_code

@app.get("/vessels", response_model=List[Dict[str, Any]])
def get_vessels(
    mmsi: Optional[int] = Query(None, description="Filter by vessel MMSI"),
    from_time: Optional[str] = Query(None, description="Filter by time range (start time, ISO format)"),
    to_time: Optional[str] = Query(None, description="Filter by time range (end time, ISO format)"),
    limit: Optional[int] = Query(100, description="Maximum number of vessels to return")
):
    """
    Get vessel data with optional filtering by MMSI and time range.
    
    - **mmsi**: Filter results to a specific vessel by MMSI
    - **from_time**: Start of time range in ISO format (e.g., "2023-04-01T12:00:00")
    - **to_time**: End of time range in ISO format (e.g., "2023-04-01T14:00:00")
    - **limit**: Maximum number of vessels to return
    """
    
    try:
        # Validate and parse time parameters
        start_time = None
        end_time = None
        
        if from_time:
            try:
                start_time = datetime.fromisoformat(from_time)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid from_time format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
                
        if to_time:
            try:
                end_time = datetime.fromisoformat(to_time)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid to_time format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
        
        # Set default time range if not specified
        if not start_time and end_time:
            # If only end_time is specified, set start_time to 2 hours before
            start_time = end_time - timedelta(hours=2)
        elif start_time and not end_time:
            # If only start_time is specified, set end_time to 2 hours after
            end_time = start_time + timedelta(hours=2)
        elif not start_time and not end_time:
            # If neither is specified, use last 1 hour as default
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build query based on filters
        query = """
        WITH latest_vessel_data AS (
            SELECT DISTINCT ON (v.vessel_id) 
                v.vessel_id,
                v.latitude AS current_latitude,
                v.longitude AS current_longitude,
                v.timestamp AS current_timestamp,
                (v.raw_json -> 'properties' ->> 'sog')::float AS sog,
                (v.raw_json -> 'properties' ->> 'cog')::float AS cog,
                (v.raw_json -> 'properties' ->> 'posAcc')::boolean AS pos_acc,
                (v.raw_json -> 'properties' ->> 'heading')::float AS heading,
                (v.raw_json -> 'properties' ->> 'navStat')::int AS nav_stat,
                v.raw_json,
                p.predicted_latitude,
                p.predicted_longitude,
                p.prediction_for_timestamp,
                p.prediction_made_at
            FROM 
                raw_ais_data v
            LEFT JOIN 
                predictions p ON v.vessel_id = p.vessel_id
            WHERE 1=1
        """
        
        # Add filters
        params = []
        
        if mmsi:
            query += " AND v.vessel_id = %s"
            params.append(mmsi)
            
        if start_time:
            query += " AND v.timestamp >= %s"
            params.append(start_time)
            
        if end_time:
            query += " AND v.timestamp <= %s"
            params.append(end_time)
            
        # Complete the query
        query += """
            ORDER BY v.vessel_id, v.timestamp DESC
        )
        SELECT * FROM latest_vessel_data
        LIMIT %s
        """
        
        params.append(limit)
        
        # Execute query
        cur.execute(query, params)
        results = cur.fetchall()
        
        vessels = []
        for row in results:
            # Extract additional data from raw_json if available
            raw_data = {}
            if row['raw_json'] and isinstance(row['raw_json'], str):
                try:
                    # Handle string JSON data
                    raw_data = json.loads(row['raw_json'])
                except json.JSONDecodeError:
                    # Don't log every failure, this is too verbose
                    pass
                except Exception:
                    # Silently handle other errors
                    pass
            elif row['raw_json'] and isinstance(row['raw_json'], dict):
                # PostgreSQL might have already parsed the JSON
                raw_data = row['raw_json']
            
            # Get vessel type and country
            vessel_type, vessel_type_code = get_vessel_type(raw_data)
            vessel_country = get_country_from_mmsi(row['vessel_id'])
            
            # Get navigation status
            nav_stat = row['nav_stat']
            vessel_status = NAV_STATUS_MAP.get(nav_stat, "Unknown") if nav_stat is not None else "Unknown"
            
            # Format vessel data
            vessel_data = {
                "vessel_id": row['vessel_id'],
                "current_latitude": row['current_latitude'],
                "current_longitude": row['current_longitude'],
                "current_timestamp": row['current_timestamp'].isoformat() if row['current_timestamp'] else None,
                "sog": float(row['sog']) if row['sog'] is not None else 0.0,
                "cog": float(row['cog']) if row['cog'] is not None else 0.0,
                "heading": float(row['heading']) if row['heading'] is not None else None,
                "pos_acc": bool(row['pos_acc']) if row['pos_acc'] is not None else False,
                "nav_stat": nav_stat,
                "vessel_status": vessel_status,
                "vessel_type": vessel_type,
                "vessel_type_code": vessel_type_code,
                "country": vessel_country
            }
            
            # Add prediction data if valid
            pred_lat = row['predicted_latitude']
            pred_lon = row['predicted_longitude']
            
            if is_valid_prediction(pred_lat, pred_lon):
                vessel_data.update({
                    "predicted_latitude": float(pred_lat),
                    "predicted_longitude": float(pred_lon),
                    "prediction_for_timestamp": row['prediction_for_timestamp'].isoformat() if row['prediction_for_timestamp'] else None,
                    "prediction_made_at": row['prediction_made_at'].isoformat() if row['prediction_made_at'] else None
                })
            else:
                vessel_data.update({
                    "predicted_latitude": None,
                    "predicted_longitude": None,
                    "prediction_for_timestamp": None,
                    "prediction_made_at": None
                })

            vessels.append(vessel_data)

        logger.info(f"API request: returned {len(vessels)} vessels (filters: mmsi={mmsi}, time range: {start_time} to {end_time})")
        return vessels
        
    except Exception as e:
        logger.error(f"Error retrieving vessel data: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving vessel data: {str(e)}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

@app.get("/health")
def health_check():
    """API health check endpoint"""
    return {
        "status": "healthy",
        "time": datetime.now().isoformat(),
        "version": app.version
    }

@app.get("/vessels/{vessel_id}", response_model=Dict[str, Any])
def get_vessel(vessel_id: int):
    """Get detailed information about a specific vessel"""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Query to get vessel details
        query = """
        SELECT 
            a.vessel_id, 
            a.latitude AS current_latitude, 
            a.longitude AS current_longitude, 
            a.timestamp AS current_timestamp,
            COALESCE((a.raw_json -> 'properties' ->> 'sog')::float, 0.0) AS sog,
            COALESCE((a.raw_json -> 'properties' ->> 'cog')::float, 0.0) AS cog,
            COALESCE((a.raw_json -> 'properties' ->> 'posAcc')::boolean, false) AS pos_acc,
            COALESCE((a.raw_json -> 'properties' ->> 'heading')::float, null) AS heading,
            COALESCE((a.raw_json -> 'properties' ->> 'navStat')::int, null) AS nav_stat,
            a.raw_json,
            p.predicted_latitude, 
            p.predicted_longitude, 
            p.prediction_for_timestamp, 
            p.prediction_made_at
        FROM raw_ais_data a
        LEFT JOIN predictions p ON a.vessel_id = p.vessel_id
        WHERE a.vessel_id = %s
        ORDER BY a.timestamp DESC
        LIMIT 1
        """
        cur.execute(query, (vessel_id,))
        vessel = cur.fetchone()
        
        if not vessel:
            raise HTTPException(status_code=404, detail=f"Vessel with ID {vessel_id} not found")
        
        # Process vessel data similarly to get_vessels
        raw_data = {}
        if vessel["raw_json"] and isinstance(vessel["raw_json"], str):
            try:
                # Handle string JSON data
                raw_data = json.loads(vessel["raw_json"])
            except json.JSONDecodeError:
                # Don't log error, this would be too verbose
                pass
            except Exception:
                # Silently handle other errors
                pass
        elif vessel["raw_json"] and isinstance(vessel["raw_json"], dict):
            # PostgreSQL might have already parsed the JSON
            raw_data = vessel["raw_json"]
            
        vessel_type, vessel_type_code = get_vessel_type(raw_data)
        vessel_country = get_country_from_mmsi(vessel["vessel_id"])
        nav_stat = vessel["nav_stat"]
        vessel_status = NAV_STATUS_MAP.get(nav_stat, "Unknown") if nav_stat is not None else "Unknown"
        
        response = {
            "vessel_id": vessel["vessel_id"],
            "current_latitude": vessel["current_latitude"],
            "current_longitude": vessel["current_longitude"],
            "current_timestamp": vessel["current_timestamp"].isoformat() if vessel["current_timestamp"] else None,
            "sog": float(vessel["sog"]) if vessel["sog"] is not None else 0.0,
            "cog": float(vessel["cog"]) if vessel["cog"] is not None else 0.0,
            "heading": float(vessel["heading"]) if vessel["heading"] is not None else None,
            "pos_acc": bool(vessel["pos_acc"]) if vessel["pos_acc"] is not None else False,
            "nav_stat": nav_stat,
            "vessel_status": vessel_status,
            "vessel_type": vessel_type,
            "vessel_type_code": vessel_type_code,
            "country": vessel_country
        }
        
        # Add prediction data if valid
        pred_lat = vessel["predicted_latitude"]
        pred_lon = vessel["predicted_longitude"]
        
        if is_valid_prediction(pred_lat, pred_lon):
            response.update({
                "predicted_latitude": float(pred_lat),
                "predicted_longitude": float(pred_lon),
                "prediction_for_timestamp": vessel["prediction_for_timestamp"].isoformat() if vessel["prediction_for_timestamp"] else None,
                "prediction_made_at": vessel["prediction_made_at"].isoformat() if vessel["prediction_made_at"] else None
            })
        else:
            response.update({
                "predicted_latitude": None,
                "predicted_longitude": None,
                "prediction_for_timestamp": None,
                "prediction_made_at": None
            })
            
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_vessel: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.get("/vessels/download")
async def download_vessels(
    mmsi: Optional[int] = Query(None, description="Filter by vessel MMSI"),
    from_time: Optional[str] = Query(None, description="Filter by time range (start time, ISO format)"),
    to_time: Optional[str] = Query(None, description="Filter by time range (end time, ISO format)"),
    format: str = Query("json", description="Output format (json or csv)")
):
    """
    Download vessel data in JSON or CSV format with optional filtering.
    
    - **mmsi**: Filter results to a specific vessel by MMSI
    - **from_time**: Start of time range in ISO format
    - **to_time**: End of time range in ISO format
    - **format**: Output format ('json' or 'csv')
    """
    
    if format not in ["json", "csv"]:
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")
    
    # Reuse get_vessels but with higher limit for downloads
    vessels = await get_vessels(mmsi, from_time, to_time, limit=10000)
    
    if format == "csv":
        # Convert to CSV
        try:
            df = pd.DataFrame(vessels)
            csv_data = df.to_csv(index=False)
            
            filename = "vessel_data.csv"
            if mmsi:
                filename = f"vessel_{mmsi}_data.csv"
                
            headers = {
                "Content-Disposition": f"attachment; filename={filename}"
            }
            return JSONResponse(content=csv_data, headers=headers, media_type="text/csv")
        except Exception as e:
            logger.error(f"Error converting to CSV: {e}")
            raise HTTPException(status_code=500, detail="Error generating CSV file")
    else:
        # Return as JSON
        filename = "vessel_data.json"
        if mmsi:
            filename = f"vessel_{mmsi}_data.json"
            
        headers = {
            "Content-Disposition": f"attachment; filename={filename}"
        }
        return JSONResponse(content=vessels, headers=headers)

if __name__ == "__main__":
    # Mount static files for the web interface
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
    
    # Use default port, remove Render.com reference
    port = 8000
    
    logger.info(f"Starting API server on 0.0.0.0:{port} (v{app.version})")
    uvicorn.run(app, host="0.0.0.0", port=port)