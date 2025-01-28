from flask import Flask, jsonify  
import sqlite3  

app = Flask(__name__)  

@app.route('/vessels')  
def get_vessels():  
    conn = sqlite3.connect('ais_data.db')  
    cursor = conn.cursor()  
    cursor.execute("SELECT * FROM vessels")  
    vessels = cursor.fetchall()  
    return jsonify(vessels)  

if __name__ == '__main__':  
    app.run(debug=True)  