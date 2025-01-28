# Maritime Vessel Tracking System

A Python-based system for collecting, processing, and visualizing maritime vessel data using AIS (Automatic Identification System) information.

## Overview

This project creates a pipeline for:
- Collecting AIS data from open maritime sources
- Processing and enriching the data using machine learning
- Storing the data in PostgreSQL
- Providing an API for data access
- Visualizing vessel movements on an interactive map

## Free Data Sources

1. **AISHub** (https://www.aishub.net/api)
   - Free tier provides access to AIS data
   - Requires registration
   - Limited to 100 requests per day
   - Data includes vessel position, speed, course

2. **MarineTraffic** (https://www.marinetraffic.com/en/ais-api-services)
   - Free developer account
   - Limited data access
   - Good documentation

3. **Danish Maritime Authority** (https://www.dma.dk/SikkerhedTilSoes/Sejladsinformation/AIS/Sider/default.aspx)
   - Free AIS data for Danish waters
   - Historical data available
   - Data in standard NMEA format

4. **U.S. Coast Guard** (https://www.navcen.uscg.gov/?pageName=AISDataFeeds)
   - Free AIS data feeds
   - Coverage of U.S. coastal waters
   - Real-time data available

## Project Structure
```
maritime_tracker/
├── data/
│   ├── raw/              # Raw AIS data storage
│   └── processed/        # Processed and enriched data
├── src/
│   ├── collector/        # Data collection scripts
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
# Edit .env with your API keys and database credentials
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

1. Collect AIS data:
```bash
python src/collector/collect_ais.py
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

## ML Models

The system uses machine learning for:
1. Vessel type classification
2. Trajectory prediction
3. Anomaly detection

Models are trained on historical AIS data using scikit-learn.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.