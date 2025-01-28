# Maritime Vessel Tracking System

A Python-based system for collecting, processing, and visualizing real-time maritime vessel data using AIS (Automatic Identification System) information from AISHub.

## Overview

This project creates a pipeline for:
- Collecting real-time AIS data from AISHub
- Processing and enriching the data using machine learning
- Storing the data in PostgreSQL
- Providing an API for data access
- Visualizing vessel movements on an interactive map

## Data Source: AISHub API

1. Register at [AISHub](https://www.aishub.net/join-us)
2. After registration, you'll receive:
   - API key
   - Access to real-time AIS data
   - 100 requests per day (free tier)
   - JSON formatted responses

### AISHub API Features
- Vessel positions (Lat/Long)
- Vessel details (MMSI, name, type)
- Navigation data (speed, course, destination)
- Rate limit: 1 request per minute
- Coverage: Global AIS network

## Project Structure
```
maritime_tracker/
├── data/
│   ├── raw/              # Raw API response storage
│   └── processed/        # Processed and enriched data
├── src/
│   ├── collector/        # AISHub API collector
│   ├── processing/       # ML processing scripts
│   ├── api/             # Flask API
│   └── visualization/    # Folium map generation
├── notebooks/           # Jupyter notebooks for analysis
├── tests/              # Unit tests
├── config.py           # Configuration settings
├── requirements.txt    # Project dependencies
└── README.md
```

## Setup

1. Clone the repository
```bash
git clone https://github.com/yourusername/maritime-tracker.git
cd maritime-tracker
```

2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Set up PostgreSQL database
```bash
# Create database
createdb maritime_db

# Run migrations
python src/db/init_db.py
```

5. Configure environment variables
```bash
cp .env.example .env
# Add your AISHub API key to .env file:
# AISHUB_API_KEY=your_api_key_here
```

## Dependencies

```
pandas==2.0.0
numpy==1.24.0
scikit-learn==1.2.0
flask==2.3.0
folium==0.14.0
psycopg2-binary==2.9.6
requests==2.28.2
python-dotenv==1.0.0
```

## Usage

1. Start the data collector:
```bash
python src/collector/aishub_collector.py
```

2. Process and enrich data:
```bash
python src/processing/enrich_data.py
```

3. Start the Flask API:
```bash
python src/api/app.py
```

4. View the map in your browser:
```
http://localhost:5000/map
```

## API Endpoints

- `GET /vessels` - List all vessels
- `GET /vessels/<mmsi>` - Get specific vessel details
- `GET /vessels/area` - Get vessels in specified area
- `GET /map` - View interactive map

## ML Features

The system uses machine learning for:
1. Vessel type classification
2. Trajectory prediction
3. Anomaly detection

Models are trained on collected AIS data using scikit-learn.

## Rate Limiting

The collector implements rate limiting to respect AISHub's limits:
- Maximum 100 requests per day
- Minimum 60 seconds between requests
- Automatic retry on failure

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.