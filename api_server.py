from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field
from typing import Literal
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import logging
from logging.handlers import RotatingFileHandler
import os
import csv
import io
from pathlib import Path
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Tuple
from datetime import datetime, timedelta, timezone
from fastapi.responses import JSONResponse
import uvicorn
from config import BOUNDS, ensure_log_dir, get_db_config

# Create logs directory if it doesn't exist
LOG_DIR = ensure_log_dir()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(str(LOG_DIR / 'api_server.log'), maxBytes=10485760, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("navicast.api")

# Constants
# Default database configuration
DEMO_MODE = os.getenv("NAVICAST_MODE", "live") == "demo"
DB_CONFIG = {} if DEMO_MODE else get_db_config()

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

class Vessel(BaseModel):
    vessel_id: int = Field(gt=0, le=999999999)
    current_latitude: float = Field(ge=-90, le=90)
    current_longitude: float = Field(ge=-180, le=180)
    current_timestamp: datetime
    sog: Optional[float] = Field(default=None, ge=0, lt=102.3)
    cog: Optional[float] = Field(default=None, ge=0, lt=360)
    heading: Optional[float] = Field(default=None, ge=0, lt=360)
    pos_acc: bool
    nav_stat: Optional[int]
    vessel_status: str
    vessel_type: str
    vessel_type_code: Optional[int]
    country: Optional[str]
    data_source: Literal["synthetic", "ais"]
    prediction_method: Optional[Literal["dead_reckoning"]]
    predicted_latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    predicted_longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    prediction_for_timestamp: Optional[datetime] = None
    prediction_made_at: Optional[datetime] = None


app = FastAPI(
    title="NAVICAST API",
    description="API for the NAVICAST vessel tracking and prediction system",
    version="1.0.0"
)

# Enable CORS for the frontend
_cors_origins = [o.strip() for o in os.getenv("NAVICAST_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load MMSI to country mapping
mmsi_country_map = {}
try:
    with (Path(__file__).parent / 'mid_to_country.csv').open(newline='') as country_file:
        mmsi_country_map = {int(row['MID']): row['Country'] for row in csv.DictReader(country_file)}
    logger.info(f"Loaded {len(mmsi_country_map)} MMSI country mappings")
except Exception as e:
    logger.warning(f"Could not load MMSI country mappings: {e}")

def get_db_connection():
    """Creates and returns a database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except Exception:
        logger.exception("Database connection failed")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
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
        
    props = raw_json.get('properties')
    if not isinstance(props, dict):
        return vessel_type, vessel_type_code
    code = props.get('shipType')
    if isinstance(code, bool):
        return vessel_type, vessel_type_code
    try:
        vessel_type_code = int(code)
        if str(vessel_type_code) != str(code) or not 0 <= vessel_type_code <= 99:
            return vessel_type, None
    except (TypeError, ValueError, OverflowError):
        return vessel_type, None
    vessel_type = SHIP_TYPE_MAP.get(vessel_type_code,
                                  SHIP_TYPE_MAP.get((vessel_type_code // 10) * 10, "Unknown"))

    return vessel_type, vessel_type_code


def _parse_iso_datetime(value: Optional[str], field_name: str) -> Optional[datetime]:
    """Parse ISO formatted datetime string."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _resolve_time_bounds(
    from_time: Optional[str],
    to_time: Optional[str]
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Determine start/end timestamps with sensible defaults."""
    start_time = _parse_iso_datetime(from_time, "from_time")
    end_time = _parse_iso_datetime(to_time, "to_time")

    if not start_time and end_time:
        start_time = end_time - timedelta(hours=2)
    elif start_time and not end_time:
        end_time = start_time + timedelta(hours=2)
    elif not start_time and not end_time:
        return None, None

    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=400, detail="from_time must be before to_time")
    return start_time, end_time


def _fetch_latest_vessels(
    mmsi: Optional[int],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    limit: int
) -> List[Dict[str, Any]]:
    """Execute vessel query and return raw database rows."""
    if DEMO_MODE:
        from demo_data import sample_rows
        return [row for row in sample_rows()
                if (mmsi is None or row['vessel_id'] == mmsi)
                and (start_time is None or row['current_timestamp'] >= start_time)
                and (end_time is None or row['current_timestamp'] <= end_time)][:limit]
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
            WITH latest_vessel_data AS (
                SELECT DISTINCT ON (v.vessel_id) 
                    v.vessel_id,
                    v.latitude AS current_latitude,
                    v.longitude AS current_longitude,
                    v.timestamp AS current_timestamp,
                    v.raw_json -> 'properties' ->> 'sog' AS sog,
                    v.raw_json -> 'properties' ->> 'cog' AS cog,
                    v.raw_json -> 'properties' ->> 'posAcc' AS pos_acc,
                    v.raw_json -> 'properties' ->> 'heading' AS heading,
                    v.raw_json -> 'properties' ->> 'navStat' AS nav_stat,
                    v.raw_json,
                    p.predicted_latitude,
                    p.predicted_longitude,
                    p.prediction_for_timestamp,
                    p.prediction_made_at
                FROM 
                    raw_ais_data v
                LEFT JOIN LATERAL (
                    SELECT predicted_latitude, predicted_longitude,
                           prediction_for_timestamp, prediction_made_at
                    FROM predictions
                    WHERE vessel_id = v.vessel_id
                    ORDER BY prediction_made_at DESC
                    LIMIT 1
                ) p ON true
                WHERE 1=1
            """

            params: List[Any] = []
            if mmsi is not None:
                query += " AND v.vessel_id = %s"
                params.append(mmsi)

            if start_time:
                query += " AND v.timestamp >= %s"
                params.append(start_time)

            if end_time:
                query += " AND v.timestamp <= %s"
                params.append(end_time)

            query += """
                ORDER BY v.vessel_id, v.timestamp DESC
            )
            SELECT * FROM latest_vessel_data
            LIMIT %s
            """

            params.append(limit)
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        if conn:
            conn.close()


def _load_raw_data(raw_json: Any) -> Dict[str, Any]:
    """Safely deserialize raw JSON payload if needed."""
    if isinstance(raw_json, dict):
        return raw_json
    if isinstance(raw_json, str):
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            return {}
    return {}


def _motion_value(value, maximum):
    try:
        number = float(value)
        return number if not isinstance(value, bool) and math.isfinite(number) and 0 <= number < maximum else None
    except (TypeError, ValueError):
        return None


def _format_vessel_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert database row into API response structure."""
    raw_data = _load_raw_data(row.get('raw_json'))
    vessel_type, vessel_type_code = get_vessel_type(raw_data)
    vessel_country = get_country_from_mmsi(row.get('vessel_id'))

    nav_value = _motion_value(row.get('nav_stat'), 16)
    nav_stat = int(nav_value) if nav_value is not None and nav_value.is_integer() else None
    vessel_status = NAV_STATUS_MAP.get(nav_stat, "Unknown") if nav_stat is not None else "Unknown"

    vessel_data = {
        "vessel_id": row.get('vessel_id'),
        "current_latitude": row.get('current_latitude'),
        "current_longitude": row.get('current_longitude'),
        "current_timestamp": row.get('current_timestamp').isoformat() if row.get('current_timestamp') else None,
        "sog": _motion_value(row.get('sog'), 102.3),
        "cog": _motion_value(row.get('cog'), 360),
        "heading": _motion_value(row.get('heading'), 360),
        "pos_acc": row.get('pos_acc') in (True, "true", "1"),
        "nav_stat": nav_stat,
        "vessel_status": vessel_status,
        "vessel_type": vessel_type,
        "vessel_type_code": vessel_type_code,
        "country": vessel_country,
        "data_source": "synthetic" if DEMO_MODE else "ais",
        "prediction_method": None
    }

    pred_lat = row.get('predicted_latitude')
    pred_lon = row.get('predicted_longitude')

    prediction_for = row.get('prediction_for_timestamp')
    if (is_valid_prediction(pred_lat, pred_lon) and prediction_for
            and prediction_for > datetime.now(timezone.utc)
            and prediction_for == row['current_timestamp'] + timedelta(minutes=30)):
        vessel_data.update({
            "prediction_method": "dead_reckoning",
            "predicted_latitude": float(pred_lat),
            "predicted_longitude": float(pred_lon),
            "prediction_for_timestamp": row.get('prediction_for_timestamp').isoformat() if row.get('prediction_for_timestamp') else None,
            "prediction_made_at": row.get('prediction_made_at').isoformat() if row.get('prediction_made_at') else None
        })
    else:
        vessel_data.update({
            "predicted_latitude": None,
            "predicted_longitude": None,
            "prediction_for_timestamp": None,
            "prediction_made_at": None
        })

    return Vessel(**vessel_data).model_dump(mode="json")

@app.get("/vessels", response_model=List[Vessel])
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
        start_time, end_time = _resolve_time_bounds(from_time, to_time)
        sanitized_limit = min(1000, max(1, limit if limit is not None else 100))
        rows = _fetch_latest_vessels(mmsi, start_time, end_time, sanitized_limit)
        vessels = [_format_vessel_row(row) for row in rows]

        logger.info(
            "API request: returned %d vessels (filters: mmsi=%s, time range: %s to %s)",
            len(vessels),
            mmsi,
            start_time,
            end_time
        )
        return vessels

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error retrieving vessel data")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/meta")
def metadata():
    return {"mode": "demo" if DEMO_MODE else "live",
            "prediction_method": "dead_reckoning", "prediction_horizon_minutes": 30}


@app.get("/health")
def health_check():
    if not DEMO_MODE:
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        except Exception:
            logger.exception("Database health check failed")
            raise HTTPException(status_code=503, detail="Database unavailable")
        finally:
            if conn:
                conn.close()
    return {"status": "healthy", "mode": "demo" if DEMO_MODE else "live",
            "time": datetime.now(timezone.utc).isoformat(), "version": app.version}

@app.get("/vessels/download")
def download_vessels(
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
    start_time, end_time = _resolve_time_bounds(from_time, to_time)
    rows = _fetch_latest_vessels(mmsi, start_time, end_time, limit=10000)
    vessels = [_format_vessel_row(row) for row in rows]
    
    if format == "csv":
        # Convert to CSV
        try:
            output = io.StringIO()
            fields = list(vessels[0]) if vessels else ['vessel_id', 'current_latitude', 'current_longitude', 'current_timestamp']
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(vessels)
            csv_data = output.getvalue()
            
            filename = "vessel_data.csv"
            if mmsi is not None:
                filename = f"vessel_{mmsi}_data.csv"
                
            headers = {
                "Content-Disposition": f"attachment; filename={filename}"
            }
            return Response(content=csv_data, media_type="text/csv", headers=headers)
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


@app.get("/vessels/{vessel_id}", response_model=Vessel)
def get_vessel(vessel_id: int):
    """Get detailed information about a specific vessel"""
    try:
        rows = _fetch_latest_vessels(vessel_id, None, None, 1)
        if not rows:
            raise HTTPException(status_code=404, detail="Vessel not found")
        return _format_vessel_row(rows[0])
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error retrieving vessel details")
        raise HTTPException(status_code=500, detail="Internal server error")

# Serve the web interface (after API routes so the "/" mount does not shadow them)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    
    logger.info(f"Starting API server on 0.0.0.0:{port} (v{app.version})")
    uvicorn.run(app, host="0.0.0.0", port=port)
