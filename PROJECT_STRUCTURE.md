# NAVICAST Project Structure

## Root Directory
- `api_server.py` - FastAPI server for the vessel data API
- `prediction_service.py` - Service that generates vessel position predictions
- `mqtt_client.py` - Client for streaming AIS data via MQTT protocol
- `vessel_prediction_model.pkl` - Trained XGBoost model for predictions
- `mid_to_country.csv` - Mapping of Maritime Identification Digits to countries
- `schema.sql` - Database schema for PostgreSQL
- `requirements.txt` - Python dependencies
- `README.md` - Project documentation
- `ML_Model.ipynb` - Jupyter notebook with model development process
- `ML_Model.pdf` - PDF version of the model notebook

## Static Directory
- `static/index.html` - Main web interface
- `static/screenshot.png` - Application screenshot
- `static/features.png` - Feature visualization
- `static/accuracy.png` - Model accuracy visualization
- `static/NAVICAST-logo/` - Logo files in various formats

## Documentation Directory
- `Documentation/architecture/` - System architecture documentation
  - `info.md` - General implementation information
  - `data_processing.ipynb` - Data processing notebook
- `Documentation/diagrams/` - System diagrams
  - `data_architecture_diagram.mmd` - Mermaid diagram source
  - `data_architecture_diagram.png` - Diagram image
  - `data_architecture_diagram.svg` - Vector diagram
  - `updated_data_architecture_diagram.mmd` - Updated diagram source
- `Documentation/reports/` - Project reports
  - `report_of_changes_4.2.txt` - Change log
  - `DMP.txt` - Data Management Plan

## Natural Earth Data
- `natural_earth_data/` - Geographic data for map visualization
  - `ne_10m_admin_0_countries.*` - Medium resolution country boundaries 