import websockets
import asyncio
import json
from database.config import DB_CONFIG

async def fetch_data():
    async with websockets.connect("wss://meri.digitraffic.fi:443/mqtt") as ws:
        while True:
            data = await ws.recv()
            save_to_db(json.loads(data))

def save_to_db(data):
    import psycopg2
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO raw_ais_data (timestamp, payload) 
        VALUES (NOW(), %s)
    """, (json.dumps(data),))
    conn.commit()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(fetch_data())