import requests  
import json  
import time  

API_URL = "https://services.marinetraffic.com/api/exportvessels/v:10/your_API_key_here"  
API_KEY = "YOUR_API_KEY"  # Get a free key from MarineTraffic/AISHub  

def fetch_ais_data():  
    response = requests.get(f"{API_URL}?api_key={API_KEY}")  
    data = response.json()  
    with open("src/raw_data.json", "w") as f:  
        json.dump(data, f)  

# Run every 5 minutes  
while True:  
    fetch_ais_data()  
    time.sleep(300)  