import paho.mqtt.client as mqtt
import json
import math
import psycopg2
import threading
from datetime import datetime, timezone
import time
import uuid
import logging
from logging.handlers import RotatingFileHandler
from config import ensure_log_dir, get_db_config

# Create logs directory if it doesn't exist
LOG_DIR = ensure_log_dir()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(str(LOG_DIR / 'mqtt_client.log'), maxBytes=10485760, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
BATCH_SIZE = 10
APP_NAME = 'Navicast/MQTT_Client_1.0'

# Database configuration
DB_CONFIG = get_db_config()

# Global variables
batch = []
batch_lock = threading.Lock()


def _normalize_timestamp_ms(raw):
    """Normalize finite positive epoch seconds or milliseconds."""
    if isinstance(raw, bool):
        raise ValueError("Invalid vessel timestamp")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid vessel timestamp") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Invalid vessel timestamp")
    # shortcut: timestamps before 2001 in milliseconds are ambiguous; use explicit feed units if needed.
    return int(value if value >= 1e12 else value * 1000)


def store_raw_data_batch(batch_data):
    """Commit valid observations; return False if the batch could not commit."""
    if not batch_data:
        return True

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        inserted_count = 0
        for vessel in batch_data:
            try:
                mmsi = vessel["mmsi"]
                if isinstance(mmsi, bool) or not str(mmsi).isdigit():
                    raise ValueError("Invalid MMSI")
                vessel_id = int(mmsi)
                if not 0 < vessel_id <= 999999999:
                    raise ValueError("Invalid MMSI")
                latitude, longitude = vessel["lat"], vessel["lon"]
                if (any(isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) for value in (latitude, longitude))
                        or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
                    raise ValueError("Invalid vessel coordinates")
                timestamp_ms = _normalize_timestamp_ms(vessel.get("time", time.time()))
                timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                props = vessel.get("properties", {})
                if not isinstance(props, dict):
                    raise ValueError("Invalid vessel properties")
                props = dict(props)
                for name, limit in (("sog", 102.3), ("cog", 360), ("heading", 360)):
                    value = props.get(name, vessel.get(name))
                    # AIS uses 102.3, 360 and 511 as unavailable values; never invent motion.
                    props[name] = (value if not isinstance(value, bool)
                                   and isinstance(value, (int, float)) and math.isfinite(value)
                                   and 0 <= value < limit else None)
                nav_status = props.get("navStat", vessel.get("navStat"))
                props["navStat"] = (nav_status if type(nav_status) is int and 0 <= nav_status <= 15 else None)
                accuracy = props.get("posAcc", vessel.get("posAcc"))
                props["posAcc"] = accuracy if isinstance(accuracy, bool) else None
                raw_json = json.dumps({**vessel, "properties": props}, allow_nan=False)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                logger.warning("Skipping invalid observation: %s", exc)
                continue

            cur.execute("SAVEPOINT ais_row")
            try:
                cur.execute(
                    "INSERT INTO raw_ais_data (vessel_id, latitude, longitude, timestamp, raw_json) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (vessel_id, latitude, longitude, timestamp_dt, raw_json)
                )
                inserted_count += cur.rowcount
            except psycopg2.Error as exc:
                cur.execute("ROLLBACK TO SAVEPOINT ais_row")
                logger.warning("Skipping rejected observation for vessel %s: %s", vessel_id, exc)
            finally:
                cur.execute("RELEASE SAVEPOINT ais_row")

        cur.execute("DELETE FROM raw_ais_data WHERE timestamp < NOW() - INTERVAL '24 hours'")
        conn.commit()
        logger.info("Inserted %s new records, cleaned up old records", inserted_count)
        return True
    except Exception as exc:
        logger.error("Database batch failed; observations were not committed: %s", exc)
        if conn:
            try:
                conn.rollback()
            except psycopg2.Error:
                logger.warning("Could not roll back a failed database connection")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _flush_batch():
    """Retain a failed batch for the next flush attempt."""
    with batch_lock:
        if store_raw_data_batch(batch):
            batch.clear()


def on_connect(client, userdata, flags, rc, properties=None):
    """Callback when connected to MQTT broker"""
    if rc == 0:
        logger.info("Connected to MQTT Broker")
        # Subscribe to vessel topics
        client.subscribe("vessels-v2/+/location", qos=1)
        logger.info("Subscribed to vessel location topics")
    else:
        logger.error(f"Failed to connect, return code {rc}")

def on_message(client, userdata, message):
    """Queue location observations with bounded buffering during DB outages."""
    try:
        data = json.loads(message.payload.decode("utf-8"))
        topic_parts = message.topic.split("/")
        if (len(topic_parts) != 3 or topic_parts[0] != "vessels-v2"
                or topic_parts[2] != "location" or not topic_parts[1].isdigit()
                or not isinstance(data, dict) or "lat" not in data or "lon" not in data):
            return
        data["mmsi"] = topic_parts[1]
        with batch_lock:
            if len(batch) >= BATCH_SIZE:
                if not store_raw_data_batch(batch):
                    logger.error("Batch buffer full; dropping incoming observation while database is unavailable")
                    return
                batch.clear()
            batch.append(data)
        if len(batch) >= BATCH_SIZE:
            _flush_batch()
    except (ValueError, UnicodeDecodeError) as exc:
        logger.warning("Skipping malformed MQTT message: %s", exc)


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    """Paho VERSION2 callback; disconnect flags are separate from reason code."""
    if reason_code != 0:
        logger.warning("Unexpected disconnection. Reason code: %s", reason_code)
    else:
        logger.info("Disconnected from MQTT Broker")
    _flush_batch()


def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    """Callback when subscribed to a topic"""
    logger.info(f"Subscribed to topics with QoS: {granted_qos}")

def main():
    """Main function to run the MQTT client"""
    client = None

    try:
        logger.info("Starting MQTT client for AIS data streaming")
        
        # Create MQTT client with unique ID
        client_id = f"{APP_NAME}_{str(uuid.uuid4())[:8]}"
        client = mqtt.Client(
            client_id=client_id,
            transport="websockets",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        
        # Set TLS for secure connection
        client.tls_set()
        
        # Set callbacks
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.on_subscribe = on_subscribe
        
        # Configure reconnection
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        
        # Connect to Digitraffic MQTT broker
        broker = "meri.digitraffic.fi"
        port = 443
        logger.info(f"Connecting to {broker}:{port}...")
        
        client.connect(broker, port, keepalive=60)
        client.loop_start()
        
        logger.info("Starting continuous MQTT ingestion")
        start_time = time.monotonic()
        next_status = start_time + 300
        try:
            while True:
                time.sleep(1)
                now = time.monotonic()
                if now >= next_status:
                    logger.info("MQTT client uptime: %.1f minutes", (now - start_time) / 60)
                    next_status = now + 300
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")

    except Exception as e:
        logger.error(f"Error in main MQTT client: {e}")
        raise
    finally:
        logger.info("Stopping MQTT client")
        if client is not None:
            client.loop_stop()
            client.disconnect()
        _flush_batch()

if __name__ == "__main__":
    main()
