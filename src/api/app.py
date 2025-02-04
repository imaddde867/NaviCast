from flask import Flask, jsonify
from flask_cors import CORS
from database.config import DB_CONFIG
import psycopg2

app = Flask(__name__)
CORS(app)

@app.route('/vessels')
def get_vessels():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT * FROM enriched_ais_data")
    vessels = cur.fetchall()
    return jsonify([{
        'id': v[0],
        'latitude': v[2],
        'longitude': v[3]
    } for v in vessels])

if __name__ == '__main__':
    app.run(port=5000)