# NAVICAST Data Management Plan

## 1. Data Collection

### 1.1 Data Sources

NAVICAST collects vessel traffic data from the following sources:

- **Primary Source**: Finnish Transport Agency's Digitraffic Marine API
- **Method**: MQTT subscription to AIS (Automatic Identification System) data feed
- **Update Frequency**: Real-time (messages received as they are broadcast by vessels)
- **Geographic Scope**: Primarily Baltic Sea region
- **Data Format**: JSON messages containing vessel position and metadata

### 1.2 Data Types

The system collects the following types of data:

- **Vessel Identification**: MMSI (Maritime Mobile Service Identity), vessel name
- **Position Data**: Latitude, longitude, accuracy
- **Movement Data**: Speed over ground (SOG), course over ground (COG), heading
- **Vessel Status**: Navigation status, vessel type
- **Temporal Data**: Timestamps of message broadcast and reception

### 1.3 Data Collection Process

1. MQTT client establishes secure connection to Digitraffic MQTT broker
2. Client subscribes to appropriate AIS message topics
3. Messages are received and decoded
4. Data is validated for completeness and format correctness
5. Validated data is prepared for database storage
6. Data is inserted into PostgreSQL database in batches for efficiency

### 1.4 Data Volume and Growth

- **Average Message Size**: ~500 bytes per AIS message
- **Message Frequency**: 50-200 messages per minute (varies with vessel traffic)
- **Daily Data Volume**: Approximately 40-160 MB raw data
- **Monthly Growth**: 1-5 GB (pre-compression)
- **Annual Growth**: 12-60 GB (pre-compression)

## 2. Data Storage

### 2.1 Storage Infrastructure

- **Database Type**: PostgreSQL 13+
- **Storage Format**: Relational database tables with JSONB for raw message storage
- **Storage Location**: Local server (primary implementation)
- **Redundancy**: Database backups recommended for production environments

### 2.2 Database Schema

The database consists of two primary tables:

**vessels table**:
- Stores current vessel information
- One row per vessel (updated with most recent data)
- Contains processed fields from AIS messages
- Includes raw JSON for reference and additional processing

**predictions table**:
- Stores trajectory predictions for vessels
- Links to vessels via vessel_id foreign key
- Contains predicted positions and timestamps
- Allows tracking of prediction accuracy over time

### 2.3 Data Retention

- **Raw AIS Data**: Retained for 30 days by default
- **Predictions**: Retained for 7 days by default
- **Retention Policy**: Configurable via database cleanup function
- **Archive Policy**: Optional archiving of historical data to compressed files

### 2.4 Data Backup

Recommended backup strategy for production deployments:

- **Frequency**: Daily database backups
- **Retention**: 7 daily backups, 4 weekly backups
- **Method**: pg_dump for PostgreSQL database
- **Verification**: Regular backup restoration tests

## 3. Data Processing

### 3.1 Data Validation

All incoming data undergoes validation:

- **Required Fields**: Vessel ID, position coordinates, timestamp
- **Range Validation**: Geographic coordinates within valid ranges
- **Type Validation**: Data types match expected formats
- **Consistency Checks**: Speed, course, and position changes are physically realistic

### 3.2 Data Enrichment

The system enhances raw AIS data with:

- **Country of Registration**: Derived from MMSI country codes
- **Vessel Type Description**: Human-readable versions of AIS type codes
- **Navigation Status Description**: Human-readable versions of status codes
- **Trajectory Predictions**: Calculated future positions

### 3.3 Prediction Processing

Vessel trajectory predictions are generated through:

1. Selection of vessels with sufficient data quality
2. Analysis of recent movement patterns (speed, course)
3. Application of prediction algorithm
4. Validation of prediction results
5. Storage of validated predictions

### 3.4 Data Cleanup

Automated data maintenance processes:

- **Outdated Data Removal**: Periodic removal of data beyond retention period
- **Duplicate Detection**: Prevention of duplicate entries
- **Invalid Data Handling**: Logging and exclusion of invalid data

## 4. Data Access and Distribution

### 4.1 Access Methods

Data is accessible through:

- **REST API**: Primary programmatic access method
- **Web Interface**: Visual representation for human users
- **Data Downloads**: Formatted exports via API endpoints

### 4.2 API Capabilities

The API provides the following capabilities:

- **Vessel Data Retrieval**: Current positions and information
- **Filtering**: By vessel ID, time range, geographic area
- **Download Formats**: JSON and CSV exports
- **Real-time Updates**: Current vessel data

### 4.3 Access Control

Currently, the system implements simple access controls:

- **API Access**: No authentication required (intended for private deployments)
- **Database Access**: Username/password authentication
- **Modifications**: API is read-only for vessel data

### 4.4 Usage Limitations

The following limitations apply to data usage:

- **Rate Limiting**: None implemented in current version
- **Attribution**: Source data from Digitraffic should be attributed accordingly
- **Redistribution**: Follow Digitraffic terms of service for data redistribution

## 5. Data Quality

### 5.1 Data Quality Measures

The system implements several measures to ensure data quality:

- **Completeness**: Required fields must be present
- **Accuracy**: Position accuracy flags are tracked
- **Timeliness**: Timestamps are recorded and displayed
- **Consistency**: Data anomalies are detected and filtered

### 5.2 Known Issues

Common data quality issues include:

- **Message Loss**: Some AIS messages may not be received
- **Position Errors**: GPS inaccuracies in vessel position
- **Stale Data**: Vessels may stop transmitting updates
- **Data Gaps**: Network disruptions may cause gaps in data collection

### 5.3 Quality Monitoring

Data quality is monitored through:

- **Logging**: Detailed logs of data processing and errors
- **Validation Metrics**: Tracking of invalid or suspicious data
- **Prediction Accuracy**: Comparing predictions to actual positions

## 6. Technical and Security Considerations

### 6.1 Infrastructure Requirements

Minimum recommended specifications:

- **CPU**: Dual-core 2.0+ GHz
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 20GB minimum for database
- **Network**: Reliable internet connection for MQTT feed

### 6.2 Security Measures

- **Data Encryption**: HTTPS for API and web interface
- **Database Security**: Password authentication and restricted network access
- **Log Security**: Logs do not contain sensitive information

### 6.3 Dependencies

The system relies on:

- **PostgreSQL**: Database for data storage
- **Python**: Application programming language
- **FastAPI**: Web framework for API
- **Paho-MQTT**: Library for MQTT communication
- **Leaflet.js**: Library for map visualization

## 7. Ethics and Privacy

### 7.1 Privacy Considerations

- **Personal Data**: The system does not collect or store personal data
- **Vessel Information**: All vessel data is from public AIS broadcasts
- **Location Privacy**: Only publicly broadcast locations are recorded

### 7.2 Ethical Use

The data should be used in accordance with:

- **Maritime Safety**: Supporting safe navigation
- **Research**: Understanding vessel traffic patterns
- **Environmental Monitoring**: Tracking potential impacts

### 7.3 Legal Compliance

- **Data Source Terms**: Usage complies with Digitraffic terms of service
- **Open Data**: AIS data is generally considered open data
- **Usage Restrictions**: Commercial use should verify compliance with data source terms

## 8. Maintenance and Updates

### 8.1 System Maintenance

Regular maintenance activities include:

- **Database Optimization**: Periodic database vacuuming
- **Log Rotation**: Automatic rotation of system logs
- **Software Updates**: Regular updates to dependencies and libraries
- **Configuration Review**: Periodic review of system configuration

### 8.2 Monitoring

System monitoring includes:

- **Service Status**: Monitoring of MQTT client, prediction service, and API server
- **Database Performance**: Monitoring of database performance and growth
- **Error Rates**: Tracking of system errors and exceptions
- **Data Flow**: Monitoring of data collection and processing rates 