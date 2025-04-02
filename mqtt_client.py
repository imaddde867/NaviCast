import paho.mqtt.client as mqtt
import json
import psycopg2
from datetime import datetime
import time
import uuid
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/mqtt_client.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
BATCH_SIZE = 10
APP_NAME = 'Navicast/MQTT_Client_1.0'
STREAM_DURATION = 3600 * 24  # 24 hours
DB_CONFIG = {
    "dbname": "ais_project",
    "user": "postgres",
    "password": "120705imad",
    "host": "localhost"
}

# Global variables
batch = []

def store_raw_data_batch(batch_data):
    """Store a batch of vessel data in the database"""
    if not batch_data:
        return
        
    logger.info(f"Processing batch with {len(batch_data)} records")
    
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        inserted_count = 0
        for vessel in batch_data:
            if "lat" not in vessel or "lon" not in vessel:
                continue
                
            # Extract and validate vessel data
            vessel_id = int(vessel.get("mmsi", 0))
            latitude = vessel["lat"]
            longitude = vessel["lon"]
            timestamp_ms = vessel.get("time", int(time.time())) * 1000
            timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
            
            # Ensure properties exist
            if "properties" not in vessel:
                vessel["properties"] = {}
            
            props = vessel["properties"]
            
            # Set default properties if missing
            for prop_name, default in [("sog", 0.0), ("cog", 0.0), ("heading", 0.0), ("posAcc", False)]:
                if prop_name not in props:
                    props[prop_name] = vessel.get(prop_name, default)
            
            # Validate property ranges
            sog = props.get("sog", 0)
            cog = props.get("cog", 0)
            heading = props.get("heading", 0)
            
            # Validate data ranges
            if not isinstance(sog, (int, float)) or not (0 <= sog <= 50):
                logger.warning(f"Adjusting vessel {vessel_id} invalid sog: {sog} to 0")
                props["sog"] = 0
                
            if not isinstance(cog, (int, float)) or not (0 <= cog <= 360):
                logger.warning(f"Adjusting vessel {vessel_id} invalid cog: {cog} to 0")
                props["cog"] = 0
                
            if heading is not None and (not isinstance(heading, (int, float)) or not (0 <= heading <= 360)):
                logger.warning(f"Adjusting vessel {vessel_id} invalid heading: {heading} to 0")
                props["heading"] = 0
            
            # Update vessel with corrected properties
            vessel["properties"] = props
            raw_json = json.dumps(vessel)
            
            # Check if record exists before inserting
            cur.execute(
                "SELECT 1 FROM raw_ais_data WHERE vessel_id = %s AND timestamp = %s LIMIT 1",
                (vessel_id, timestamp_dt)
            )
            
            if cur.fetchone() is None:
                # Record doesn't exist, insert it
                cur.execute(
                    "INSERT INTO raw_ais_data (vessel_id, latitude, longitude, timestamp, raw_json) VALUES (%s, %s, %s, %s, %s)",
                    (vessel_id, latitude, longitude, timestamp_dt, raw_json)
                )
                inserted_count += 1
        
        # Clean up old records (older than 24 hours)
        cur.execute("DELETE FROM raw_ais_data WHERE timestamp < NOW() - INTERVAL '24 hours'")
        
        conn.commit()
        logger.info(f"Inserted {inserted_count} new records, cleaned up old records")
        
    except Exception as e:
        logger.error(f"Database error: {e}")
        if conn:
            conn.rollback()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback when connected to MQTT broker"""
    if rc == 0:
        logger.info("Connected to MQTT Broker")
        # Subscribe to vessel topics
        client.subscribe("vessels-v2/#", qos=1)
        client.subscribe("vessels-v2/+/location", qos=1)
        client.subscribe("vessels-v2/status", qos=1)
        logger.info("Subscribed to vessel location topics")
    else:
        logger.error(f"Failed to connect, return code {rc}")

def on_message(client, userdata, message, properties=None):
    """Callback when message is received"""
    global batch
    
    try:
        payload = message.payload.decode('utf-8')
        
        # Parse JSON payload
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
            
        # Extract vessel ID from topic
        topic_parts = message.topic.split('/')
        if len(topic_parts) >= 2 and topic_parts[0] == "vessels-v2":
            mmsi = topic_parts[1]
            
            try:
                mmsi_int = int(mmsi)
                # Only process valid MMSI numbers
                if mmsi_int > 0 and isinstance(data, dict) and "lat" in data and "lon" in data:
                    data["mmsi"] = mmsi
                    logger.info(f"Received vessel data for MMSI {mmsi}: lat={data['lat']}, lon={data['lon']}")
                    
                    # Add to batch
                    batch.append(data)
                    
                    # Process batch when it reaches the threshold
                    if len(batch) >= BATCH_SIZE:
                        store_raw_data_batch(batch)
                        batch = []
            except ValueError:
                # Not a numeric MMSI
                pass

    except Exception as e:
        logger.error(f"Error processing message: {e}")

def on_disconnect(client, userdata, rc, properties=None, reason=None):
    """Callback when disconnected from MQTT broker"""
    if rc != 0:
        logger.warning(f"Unexpected disconnection. Reason code: {rc}")
    else:
        logger.info("Disconnected from MQTT Broker")
    
    # Process any remaining batch items
    if batch:
        store_raw_data_batch(batch)

def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    """Callback when subscribed to a topic"""
    logger.info(f"Subscribed to topics with QoS: {granted_qos}")

def main():
    """Main function to run the MQTT client"""
    global batch
    
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
        
        # Run for specified duration
        logger.info(f"Starting the MQTT loop for {STREAM_DURATION/3600:.1f} hours")
        start_time = time.time()
        
        try:
            while time.time() - start_time < STREAM_DURATION:
                time.sleep(1)
                
                # Log status every 5 minutes
                if int(time.time() - start_time) % 300 == 0:
                    uptime_minutes = (time.time() - start_time) / 60
                    logger.info(f"MQTT client uptime: {uptime_minutes:.1f} minutes")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        
        # Process any remaining items in batch
        if batch:
            logger.info(f"Processing remaining {len(batch)} items in batch")
            store_raw_data_batch(batch)
            batch = []

    except Exception as e:
        logger.error(f"Error in main MQTT client: {e}")
    finally:
        logger.info("Stopping MQTT client")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()