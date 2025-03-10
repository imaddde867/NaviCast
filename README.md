# NAVICAST: Real-Time Vessel Tracking and Prediction System

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.95.0-009688)](https://fastapi.tiangolo.com/)
[![XGBoost](https://img.shields.io/badge/XGBoost-Machine%20Learning-yellow)](https://xgboost.readthedocs.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-blue)](https://www.postgresql.org/)

<p align="center">
  <img src="static/NAVICAST-logo/logo-white.svg" alt="NAVICAST Logo" width="300">
</p>

<p align="center">
  <img src="static/screenshot.png" alt="NAVICAST Screenshot" width="600">
</p>

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Performance Metrics](#performance-metrics)
- [Future Improvements](#future-improvements)
- [Acknowledgments](#acknowledgments)
- [Contact](#contact)

## Overview
NAVICAST is an innovative, real-time vessel tracking and prediction system focused on the Baltic Sea region. Leveraging Automatic Identification System (AIS) data streamed from Digitraffic, NAVICAST visualizes the current positions of 913 vessels (as of March 10, 2025) and employs a state-of-the-art machine learning model to predict their future positions. Built with a passion for machine learning and data engineering, this project combines robust data pipelines, advanced ML techniques, and an interactive, smooth graphical interface.

## Features
- **Real-Time Tracking**: Monitors and displays the current positions of vessels in the Baltic Sea using AIS data.
- **Predictive Analytics**: Utilizes a tuned XGBoost model to forecast vessel positions 30 minutes ahead, with impressive metrics:
  - Overall MSE: 1.433
  - Lat MSE: 0.3941
  - Lon MSE: 2.4719
  - MAE: 0.4381
  - R²: 0.7621
- **Interactive Visualization**: A sleek, responsive web interface built with Leaflet.js, featuring:
  - Current and predicted vessel positions (distinguished by blue and orange markers)
  - Predicted paths with dashed lines
  - Auto-refresh every 10 seconds for up-to-date data
  - Toggleable prediction display and map centering on the Baltic Sea
- **Data Pipeline**: Integrates MQTT streaming, PostgreSQL storage, and batch processing for efficient data handling.
- **ML Optimization**: Employs Optuna for hyperparameter tuning of the XGBoost model, ensuring optimal performance.

<p align="center">
  <img src="static/features.png" alt="NAVICAST Features Visualization" width="500">
  <br><em>Visual representation of the tracking key features presented in the UI</em>
</p>

## Tech Stack
- **Frontend**: HTML, CSS, Leaflet.js
- **Backend**: FastAPI, Python
- **Database**: PostgreSQL
- **Machine Learning**: XGBoost, Optuna, Scikit-learn
- **Data Streaming**: Paho MQTT, Digitraffic AIS feed
- **Additional Libraries**: Pandas, GeoPandas, Matplotlib, NumPy

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/imaddde867/Maritime-Vessel-Tracking-System.git
cd navicast
```

### 2. Set Up Environment
```bash
# Install Python 3.9+ and create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Database
- Set up a PostgreSQL database with the appropriate credentials.
- Start the PostgreSQL service:
  ```bash
  # On Linux/MacOS (example with Homebrew on MacOS)
  brew services start postgresql

  # On Windows (if using a PostgreSQL installer)
  # Ensure the service is running via Services app or command line
  ```
- Create the database and tables:
  ```bash
  psql -U your_username -d postgres -f schema.sql
  ```
  Alternatively, manually create the required tables:
  ```sql
  CREATE TABLE raw_ais_data (
      id SERIAL PRIMARY KEY,
      vessel_id INTEGER,          -- MMSI as the vessel identifier
      latitude FLOAT,            -- Latitude from geometry.coordinates[1]
      longitude FLOAT,           -- Longitude from geometry.coordinates[0]
      timestamp TIMESTAMP,       -- Converted from timestampExternal
      raw_json JSONB             -- Full JSON feature for reference
  );

  CREATE TABLE predictions (
      vessel_id BIGINT PRIMARY KEY,
      predicted_latitude DOUBLE PRECISION,
      predicted_longitude DOUBLE PRECISION,
      prediction_for_timestamp TIMESTAMP,
      prediction_made_at TIMESTAMP
  );
  ```

### 4. Run the Application
```bash
# Start the MQTT client
python mqtt_client.py

# Start the prediction service
python prediction_service.py

# Start the MQTT streaming service
python ais_streaming.py

# Start the FastAPI server
python api_server.py
```

### 5. Access the Application
Open [http://localhost:8000](http://localhost:8000) in your browser to view the interface.

## Project Structure
```
navicast/
├── static/              # Frontend files (HTML, CSS, JS)
│   ├── accuracy.png     # Prediction visualization
│   ├── features.png     # Features used in ML model
├── api_server.py        # FastAPI backend
├── ais_streaming.py     # MQTT data streaming
├── prediction_service.py # ML prediction generation
├── vessel_prediction_model.pkl # Trained XGBoost model
├── requirements.txt     # Python dependencies
├── README.md            # This file
└── schema.sql           # Database schema
```

## How It Works
1. **Data Ingestion**: AIS data is streamed in real-time from Digitraffic via MQTT, processed in batches, and stored in PostgreSQL.
2. **Prediction Generation**: A tuned XGBoost model predicts vessel positions based on features like speed, course, and time differences, with results stored in the `predictions` table.
3. **Visualization**: The frontend fetches data via the FastAPI endpoint `/vessels`, rendering it on an interactive map with current and predicted positions.

## Performance Metrics

| Model             | Overall MSE | Lat MSE | Lon MSE | MAE   | R²    |
|-------------------|-------------|---------|---------|-------|-------|
| Linear Regression | 1.4630      | 0.4469  | 2.4791  | 0.4539| 0.7449|
| Polynomial Reg.   | 1.4488      | 0.4310  | 2.4666  | 0.4472| 0.7497|
| Random Forest     | 1.8168      | 0.5227  | 3.1109  | 0.5486| 0.6898|
| XGBoost           | 1.4958      | 0.4444  | 2.5473  | 0.4505| 0.7417|
| **XGBoost (Tuned)** | **1.433** | **0.3941** | **2.4719** | **0.4381** | **0.7621** |

<p align="center">
  <img src="static/accuracy.png" alt="NAVICAST Prediction Results" width="500">
  <br><em>Comparison of predicted vs. actual vessel positions</em>
</p>

## Future Improvements
- Integrate more advanced ML models (e.g., LSTM for time-series data).
- Enhance the UI with vessel details and historical tracks.
- Deploy on a cloud service for global accessibility.

## Acknowledgments
- Digitraffic for providing real-time AIS data.
- The open-source community for tools like Leaflet.js, XGBoost, and PostgreSQL.

## Contact
Created by Imad Eddine

- Email: imadeddine200507@gmail.com
- LinkedIn: [www.linkedin.com/in/imad-eddine-el-mouss-986741262](https://www.linkedin.com/in/imad-eddine-el-mouss-986741262)