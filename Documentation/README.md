# Maritime Vessel Tracking System

## Student Information
- **Name:** Imad Eddine EL MOUSS
- **Project:** Real-time Maritime Vessel Tracking using AIS Data

## Project Structure
```
DEP_PROJ_53/
├── Documentation/
│   ├── data_architecture_diagram.mmd    # Mermaid diagram source
│   ├── data_architecture_diagram.png    # Architecture diagram image
│   └── data_architecture_diagram.svg    # Vector version of diagram
│
├── src/
│   ├── data/
│   │   ├── processed/                   # Processed AIS data
│   │   └── raw/                         # Raw API responses
│   │
│   ├── api.py                          # Flask API implementation
│   ├── data_collect.py                 # AISHub data collector
│   ├── data_enrichment.ipynb           # ML processing notebook
│   └── Visualising.py                  # Folium map generation
│
└── README.md                           # Project documentation
```

## Overview
This project creates a real-time maritime vessel tracking system using AIS (Automatic Identification System) data from AISHub. The system collects, processes, and visualizes vessel movements through an interactive web interface.

## Components

### 1. Data Collection (`data_collect.py`)
- Connects to AISHub API
- Stores raw JSON responses

### 2. Data Processing (`data_enrichment.ipynb`)
- Cleans and processes AIS data
- Implements ML models for:
  - Vessel trajectory prediction
  - Vessel type classification
  - Anomaly detection

### 3. API (`api.py`)
- Flask-based REST API
- Endpoints for vessel data and statistics
- Query interface for processed data

### 4. Visualization (`Visualising.py`)
- Interactive Folium map
- Real-time vessel positions
- Route visualization

## Dependencies
- Python 3.8+
- Flask
- Folium
- Pandas
- Scikit-learn
- Requests
- Python-dotenv

## License
This project is part of academic coursework at TUAS.