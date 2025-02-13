from ais_collector import AISDataCollector
import pandas as pd
pd.set_option('display.max_columns', None)

def test_collector():
    # Initialize collector
    collector = AISDataCollector()
    
    # Fetch and process data
    data = collector.get_latest_data()
    
    # Print summary of collected data
    if 'locations' in data and not data['locations'].empty:
        print("\nVessel Locations Summary:")
        print(f"Total vessels: {len(data['locations'])}")
        print("\nSample location data:")
        print(data['locations'].head())
        
    if 'vessels' in data and not data['vessels'].empty:
        print("\nVessel Metadata Summary:")
        print(f"Total vessels with metadata: {len(data['vessels'])}")
        print("\nSample vessel metadata:")
        print(data['vessels'].head())

if __name__ == "__main__":
    test_collector()