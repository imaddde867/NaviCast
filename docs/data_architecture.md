# NAVICAST Data Architecture

This document describes the data architecture of the NAVICAST system, detailing how data flows through the system from collection to visualization.

## Overview Diagram

![System Architecture Diagram](static/diagram.png)

## Components and Data Flow

### 1. Data Collection

**AIS Data Feed (Digitraffic)**
- Source of real-time vessel position and information data
- Provides AIS messages via MQTT protocol
- Data includes vessel identification, position, speed, course, etc.
- Messages follow standard AIS format with Digitraffic-specific extensions

**MQTT Client**
- Subscribes to Digitraffic AIS topics
- Processes incoming AIS messages
- Validates and transforms data
- Batches messages for efficient database insertion
- Handles network issues and connection recovery

**Data Flow**:
1. Digitraffic publishes AIS messages to MQTT topics
2. MQTT client subscribes to relevant topics
3. Client receives messages, validates them, and prepares for storage
4. Validated data is inserted into the PostgreSQL database

### 2. Data Storage

**PostgreSQL Database**
- Relational database storing all vessel and prediction data
- Primary tables:
  - `vessels`: Current vessel information
  - `predictions`: Vessel trajectory predictions

**Schema Details**:

`vessels` table:
- `vessel_id` (INTEGER, PRIMARY KEY): MMSI number of the vessel
- `latitude` (DOUBLE PRECISION): Current latitude
- `longitude` (DOUBLE PRECISION): Current longitude
- `sog` (DOUBLE PRECISION): Speed over ground in knots
- `cog` (DOUBLE PRECISION): Course over ground in degrees
- `heading` (INTEGER): Heading in degrees
- `nav_stat` (INTEGER): Navigation status code
- `pos_acc` (BOOLEAN): Position accuracy indicator
- `timestamp` (TIMESTAMP): Time when data was recorded
- `raw_json` (JSONB): Original AIS message in JSON format

`predictions` table:
- `id` (SERIAL, PRIMARY KEY): Unique identifier
- `vessel_id` (INTEGER, FOREIGN KEY): References vessels(vessel_id)
- `latitude` (DOUBLE PRECISION): Predicted latitude
- `longitude` (DOUBLE PRECISION): Predicted longitude
- `prediction_for_timestamp` (TIMESTAMP): Time for which prediction is made
- `prediction_made_at` (TIMESTAMP): Time when prediction was calculated

### 3. Data Processing

**Prediction Service**
- Periodically processes latest vessel data
- Analyzes vessel speed, course, and heading
- Calculates predicted positions
- Stores prediction results in database
- Performs data validation and sanity checks

**Processing Steps**:
1. Retrieve recent vessel data from database
2. Filter vessels appropriate for prediction (e.g., moving vessels)
3. For each vessel:
   - Apply prediction algorithm
   - Validate prediction results
   - Store valid predictions in database
4. Remove outdated predictions

### 4. Data Access and API

**API Server**
- Provides REST API endpoints for data access
- Retrieves vessel and prediction data from database
- Formats responses as JSON
- Allows filtering data by vessel ID and time range
- Provides data download capabilities

**Key Endpoints**:
- `GET /vessels`: Retrieves vessel data with optional filtering
- `GET /vessels/download`: Downloads vessel data in JSON or CSV format

**Data Enrichment**:
- The API enhances raw data with:
  - Country information derived from MMSI
  - Human-readable vessel type names
  - Navigation status descriptions

### 5. Data Visualization

**Web Frontend**
- Displays vessels on interactive map
- Shows vessel information in popup panels
- Visualizes predicted trajectories
- Updates in real-time
- Provides user controls for display options

**Visualization Flow**:
1. Frontend requests data from API server
2. API server retrieves and returns formatted data
3. Frontend renders vessels on map
4. Frontend updates vessel positions periodically
5. User interactions trigger additional data requests

## Data Retention and Management

- **Raw AIS Data**: Stored for 30 days by default
- **Predictions**: Stored until superseded by newer predictions
- **Data Cleanup**: Automated process removes old data
- **Backup**: Regular database backups recommended

## Data Security Considerations

- No personal information is stored in the system
- AIS data is publicly available maritime information
- Database access should be restricted to application components
- API does not require authentication in current implementation

## Data Monitoring

- System logs track data processing and errors
- API requests are logged for monitoring
- Database performance should be monitored
- Prediction quality can be evaluated by comparing predictions to actual positions 