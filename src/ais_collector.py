import requests
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
from config.config import active_config as config

# Set up logging
logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

class AISDataCollector:
    """
    Collector for AIS (Automatic Identification System) data from Digitraffic Maritime API.
    Handles both vessel locations and metadata.
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'MaritimeTrackingSystem/1.0'
        })
        
    def fetch_vessel_locations(self) -> Optional[Dict]:
        """
        Fetch current vessel locations from the API.
        Returns processed location data or None if request fails.
        """
        try:
            response = self.session.get(config.AIS_LOCATIONS_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Successfully fetched {len(data.get('features', []))} vessel locations")
            return data
            
        except requests.RequestException as e:
            logger.error(f"Error fetching vessel locations: {e}")
            return None
            
    def fetch_vessel_metadata(self) -> Optional[Dict]:
        """
        Fetch vessel metadata from the API.
        Returns vessel metadata or None if request fails.
        """
        try:
            response = self.session.get(config.AIS_VESSELS_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Successfully fetched metadata for {len(data)} vessels")
            return data
            
        except requests.RequestException as e:
            logger.error(f"Error fetching vessel metadata: {e}")
            return None

    def process_location_data(self, raw_data: Dict) -> List[Dict]:
        """
        Process raw location JSON data into a structured format.
        """
        processed_locations = []
        
        if not raw_data or 'features' not in raw_data:
            logger.warning("No features found in location data")
            return processed_locations
            
        for feature in raw_data['features']:
            try:
                location = {
                    'mmsi': feature['mmsi'],
                    'timestamp': datetime.now().isoformat(),
                    'longitude': feature['geometry']['coordinates'][0],
                    'latitude': feature['geometry']['coordinates'][1],
                    'sog': feature['properties'].get('sog', 0),  # Speed Over Ground
                    'cog': feature['properties'].get('cog', 0),  # Course Over Ground
                    'nav_status': feature['properties'].get('navStat'),
                    'heading': feature['properties'].get('heading'),
                    'data_source': feature['properties'].get('source')
                }
                processed_locations.append(location)
                
            except KeyError as e:
                logger.error(f"Error processing location feature: {e}")
                continue
                
        return processed_locations

    def process_vessel_metadata(self, raw_data: List[Dict]) -> List[Dict]:
        """
        Process raw vessel metadata into a structured format.
        """
        processed_vessels = []
        
        for vessel in raw_data:
            try:
                vessel_data = {
                    'mmsi': vessel.get('mmsi'),
                    'name': vessel.get('name'),
                    'ship_type': vessel.get('shipType'),
                    'destination': vessel.get('destination'),
                    'draught': vessel.get('draught'),
                    'timestamp': datetime.now().isoformat()
                }
                processed_vessels.append(vessel_data)
                
            except KeyError as e:
                logger.error(f"Error processing vessel metadata: {e}")
                continue
                
        return processed_vessels

    def get_latest_data(self) -> Dict[str, pd.DataFrame]:
        """
        Fetch and process both location and metadata, returning as pandas DataFrames.
        """
        # Fetch raw data
        locations_raw = self.fetch_vessel_locations()
        vessels_raw = self.fetch_vessel_metadata()
        
        # Process locations
        locations_processed = self.process_location_data(locations_raw) if locations_raw else []
        locations_df = pd.DataFrame(locations_processed)
        
        # Process vessel metadata
        vessels_processed = self.process_vessel_metadata(vessels_raw) if vessels_raw else []
        vessels_df = pd.DataFrame(vessels_processed)
        
        return {
            'locations': locations_df,
            'vessels': vessels_df
        }

    def save_raw_data(self, data: Dict, data_type: str):
        """
        Save raw JSON data to file for backup/debugging purposes.
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"data/raw/{data_type}_{timestamp}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(data, f)
            logger.debug(f"Saved raw {data_type} data to {filename}")
        except IOError as e:
            logger.error(f"Error saving raw data: {e}")