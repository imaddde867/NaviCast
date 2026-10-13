# Data management

## Sources and fields

Demo mode generates four synthetic vessel records locally. It does not ingest or store real AIS messages.

Live mode receives AIS messages from the Digitraffic Marine MQTT feed. The pipeline stores vessel identifiers (MMSI), position, speed, course, heading, status fields, timestamps, and the source message as JSONB. Prediction rows contain estimated positions and their target and creation times.

## Storage and retention

Live data is stored in PostgreSQL. The MQTT client deletes raw position rows older than 24 hours; the prediction service deletes prediction rows older than one hour. These are code-defined retention periods, not configurable retention controls. Back up or delete the database according to the deployment's operational needs.

`schema.sql` initializes missing tables and indexes without deleting existing records. It is not a versioned migration system.

## Access and limits

The API does not authenticate callers. Restrict live API and database access to trusted networks and protect database credentials. Public AIS data can still expose vessel movement patterns when collected over time.

The demo dataset is synthetic. Demo and live predictions use straight-line dead reckoning for a 30-minute horizon; they are estimates for visualization and are not suitable for navigation or safety decisions. The archived model notebook is research material and is not used to serve predictions.
