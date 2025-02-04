import requests
from database.config import DB_CONFIG
import psycopg2

def fetch_historical_data():
    url = "https://meri.digitraffic.fi/api/ais/v1/locations"
    response = requests.get(url)
    data = response.json()
    save_to_db(data)

def save_to_db(data):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO raw_ais_data (timestamp, payload) 
        VALUES (NOW(), %s)
    """, (json.dumps(data),))
    conn.commit()

if __name__ == "__main__":
    fetch_historical_data()