# NAVICAST Data Management Plan

## 1. Data Collection

### 1.1 Data Sources
- Finnish Transport Agency's Digitraffic Marine API via MQTT
- Real-time AIS data from Baltic Sea region
- JSON format containing vessel positions and metadata

### 1.2 Data Types
- Vessel identification (MMSI, name)
- Position (lat/long)
- Movement (speed, course, heading)
- Status and timestamps

### 1.3 Collection Process
- MQTT client subscribes to Digitraffic broker
- Messages validated and stored in PostgreSQL

### 1.4 Volume
- 50-200 messages/minute (~500 bytes each)
- 40-160 MB daily, 12-60 GB annually

## 2. Data Storage

### 2.1 Infrastructure
- PostgreSQL 13+ with JSONB storage
- Local server with backup redundancy

### 2.2 Schema
- `raw_ais_data`: Current vessel information
- `predictions`: Trajectory predictions

### 2.3 Retention
- Raw data: 24 hours (configurable)
- Predictions: Until superseded

## 3. Data Processing

### 3.1 Validation
- Required fields, range and type validation
- Consistency checks for realistic movement

### 3.2 Enrichment
- Country codes, vessel type descriptions
- Trajectory predictions

### 3.3 Prediction Processing
- ML model with dead reckoning fallback
- Based on recent movement patterns

## 4. Data Access

### 4.1 Methods
- REST API, web interface, data exports

### 4.2 Capabilities
- Vessel data retrieval and filtering
- JSON/CSV downloads

### 4.3 Access Control
- No authentication (private deployments)
- Database protected by username/password

## 5. Data Quality

### 5.1 Measures
- Completeness, accuracy, timeliness
- Anomaly detection

### 5.2 Known Issues
- Message loss, position errors, data gaps

## 6. Technical Requirements

### 6.1 Infrastructure
- Dual-core CPU, 8GB RAM recommended
- 20GB storage, reliable internet

### 6.2 Dependencies
- PostgreSQL 13+, Python 3.9+
- FastAPI, Paho-MQTT, Psycopg2, Pandas, Scikit-learn

## 7. Ethics and Privacy

### 7.1 Considerations
- No personal data collected
- Only public AIS broadcasts stored

### 7.2 Legal Compliance
- Follows Digitraffic terms of service
- AIS data generally considered open data

## 8. Maintenance

### 8.1 Regular Tasks
- Database optimization, log rotation
- Software updates, configuration review

### 8.2 Monitoring
- Service status, database performance
- Error rates, data flow