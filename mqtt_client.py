import paho.mqtt.client as mqtt
import json
import psycopg2
from datetime import datetime, timedelta
import time
import uuid

# Batch storage
batch = []
BATCH_SIZE = 1  # Temporarily set to 1 for testing

# Application name for client identification
APP_NAME = 'Imad/AIS_Streaming_App_1.0'

# Store raw data in PostgreSQL (batch processing)
def store_raw_data_batch(batch):
    print(f"{time.ctime()}: Starting store_raw_data_batch with {len(batch)} records")
    try:
        conn = psycopg2.connect(
            dbname="ais_project",
            user="postgres",
            password="120705imad",
            host="localhost"
        )
        cur = conn.cursor()

        values = []
        for vessel in batch:
            if "lat" in vessel and "lon" in vessel:
                vessel_id = int(vessel.get("mmsi", 0))
                latitude = vessel["lat"]
                longitude = vessel["lon"]
                timestamp_ms = vessel["time"] * 1000
                raw_json = json.dumps(vessel)
                properties = vessel.get("properties", {})
                sog = properties.get("sog", 0)
                cog = properties.get("cog", 0)
                heading = properties.get("heading", 0)

                if not (0 <= sog <= 50):
                    print(f"{time.ctime()}: Skipped vessel {vessel_id} due to invalid sog: {sog}")
                    continue
                if not (0 <= cog <= 360):
                    print(f"{time.ctime()}: Skipped vessel {vessel_id} due to invalid cog: {cog}")
                    continue
                if heading is not None and not (0 <= heading <= 360):
                    print(f"{time.ctime()}: Skipped vessel {vessel_id} due to invalid heading: {heading}")
                    continue

                timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
                values.append((vessel_id, latitude, longitude, timestamp_dt, raw_json))
            else:
                print(f"{time.ctime()}: Skipped invalid message: {vessel}")

        if values:
            cur.executemany(
                """
                INSERT INTO raw_ais_data (vessel_id, latitude, longitude, timestamp, raw_json)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (vessel_id, timestamp) DO NOTHING
                """,
                values
            )
            conn.commit()
            print(f"{time.ctime()}: Committed insertion of {len(values)} records")
        else:
            print(f"{time.ctime()}: No valid records to insert")

        cur.execute(
            """
            DELETE FROM raw_ais_data
            WHERE timestamp < NOW() - INTERVAL '24 hours'
            """
        )
        conn.commit()
        print(f"{time.ctime()}: Cleaned up old records")

    except Exception as e:
        print(f"{time.ctime()}: Error storing batch: {e}")
    finally:
        cur.close()
        conn.close()
        
# MQTT callback functions
def on_connect(client, userdata, flags, rc, properties=None):
    current_time = time.ctime()
    if rc == 0:
        print(f"{current_time}: Connected to MQTT Broker")
        client.subscribe("vessels-v2/#")
        client.subscribe("vessels-v2/+/locations")
        client.subscribe("vessels-v2/status")
        print(f"{current_time}: Subscribed to vessels-v2/+/locations and vessels-v2/status")
    else:
        print(f"{current_time}: Failed to connect, return code {rc}")

# Increase runtime or remove limit for testing
STREAM_DURATION = 3600 * 24  # 24 hours

def on_message(client, userdata, message, properties=None):
    global batch
    try:
        current_time = time.ctime()
        data = json.loads(message.payload.decode('utf-8'))
        print(f"{current_time}: Received AIS message on topic {message.topic}: {data}")

        # Log all messages for debugging
        if "lat" in data and "lon" in data:
            data["mmsi"] = message.topic.split("/")[1]
            batch.append(data)
            print(f"{current_time}: Added to batch: lat={data['lat']}, lon={data['lon']}")
        else:
            print(f"{current_time}: Message skipped (no lat/lon): {data}")

        if len(batch) >= BATCH_SIZE:
            store_raw_data_batch(batch)
            batch = []

    except Exception as e:
        print(f"{current_time}: Error processing message: {e}")


def on_disconnect(client, userdata, rc, properties=None, reason=None):
    current_time = time.ctime()
    print(f"{current_time}: Disconnected from MQTT Broker with reason code {rc}")
    if rc != 0:
        print(f"{current_time}: Unexpected disconnection. Reason: {reason}")
    if batch:
        store_raw_data_batch(batch)

def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    current_time = time.ctime()
    print(f"{current_time}: Subscribed to topics with QoS: {granted_qos}")

# Main function
if __name__ == "__main__":
    try:
        client_id = f"{APP_NAME}; {str(uuid.uuid4())}"
        client = mqtt.Client(
            client_id=client_id,
            transport="websockets",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        client.tls_set()
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.on_subscribe = on_subscribe
        client.reconnect_delay_set(min_delay=1, max_delay=120)
        client.connect("meri.digitraffic.fi", 443, keepalive=60)
        client.loop_start()

        STREAM_DURATION = 3600
        start_time = time.time()
        while time.time() - start_time < STREAM_DURATION:
            time.sleep(1)

    except Exception as e:
        print(f"{time.ctime()}: Error during execution: {e}")
    finally:
        client.loop_stop()
        client.disconnect()
        print(f"{time.ctime()}: Streaming stopped after duration limit")