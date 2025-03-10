- requests: For fetching data from the AIS API.
- pandas: For data manipulation and cleaning.
- psycopg2-binary: For connecting Python to PostgreSQL.
- flask: For building the API.
- folium: For creating interactive maps.
- tensorflow: For training and running machine learning models.

**AFTER THAT :e**  

CREATE TABLE raw_ais_data (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER,          -- MMSI as the vessel identifier
    latitude FLOAT,            -- Latitude from geometry.coordinates[1]
    longitude FLOAT,           -- Longitude from geometry.coordinates[0]
    timestamp TIMESTAMP,       -- Converted from timestampExternal
    raw_json JSONB             -- Full JSON feature for reference
);

For each feature in the features array:

vessel_id: Extract the mmsi (e.g., 219598000).
latitude: Extract geometry.coordinates[1] (e.g., 55.770832).
longitude: Extract geometry.coordinates[0] (e.g., 20.85169).
timestamp: Convert properties.timestampExternal (a Unix timestamp in milliseconds) to a PostgreSQL TIMESTAMP.
raw_json: Store the entire feature as a JSONB object.

**The timestampExternal field is more appropriate for the timestamp column than the timestamp field, as the latter (e.g., 59) likely represents seconds since the last report, while timestampExternal (e.g., 1659212938646) provides an absolute time.**


**then i created a new table for enriched data:**  

ais_project=# CREATE TABLE predictions (
    vessel_id BIGINT PRIMARY KEY,
    predicted_latitude DOUBLE PRECISION,
    predicted_longitude DOUBLE PRECISION,
    prediction_for_timestamp TIMESTAMP,
    prediction_made_at TIMESTAMP
);


               List of relations
 Schema |       Name        | Type  |  Owner   
--------+-------------------+-------+----------
 public | predictions       | table | postgres
 public | raw_ais_data      | table | postgres



 instead of runninng a script to fetch the data from the api and save it to the json and to postgresql every 10 minuttes for 48 hours. 
 we'll use WebSocket Streaming

The WebSocket protocol allows for a persistent connection between our client (our Python script) and the server (Digitraffic’s API). Unlike HTTP polling (e.g., fetching data every 5 minutes), WebSocket streaming:

Provides real-time updates as soon as new AIS messages are received by the server.
Reduces latency since you don’t have to wait for the next polling interval.
Is more efficient for high-frequency updates, as it avoids repeated HTTP requests.

However, streaming generates a much higher volume of data (potentially gigabytes per day), so we’ll need to handle this carefully to avoid overwhelming our system.

so we wrote a script that :

Connects to Finland's maritime MQTT feed via WebSocket, subscribing to real-time vessel locations in the Baltic Sea (55-60°N, 15-25°E)
Batches 100 records at a time into PostgreSQL (positions + raw JSON), running for 1 hour automatically
Key tech: MQTT-over-WebSocket → Geo-filtering → PostgreSQL batch inserts.