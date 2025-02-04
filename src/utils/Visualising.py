import matplotlib.pyplot as plt
import psycopg2
from database.config import DB_CONFIG

def plot_vessel_trajectory(vessel_id):
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql(f"SELECT * FROM enriched_ais_data WHERE vessel_id = {vessel_id}", conn)
    
    plt.figure(figsize=(10, 6))
    plt.plot(df['longitude'], df['latitude'], marker='o', linestyle='-')
    plt.title(f"Trajectory of Vessel {vessel_id}")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.grid(True)
    plt.savefig(f"trajectory_{vessel_id}.png")
    plt.close()

def plot_heatmap():
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql("SELECT latitude, longitude FROM enriched_ais_data", conn)
    
    plt.figure(figsize=(12, 8))
    plt.hexbin(df['longitude'], df['latitude'], gridsize=50, cmap='viridis')
    plt.colorbar(label='Density')
    plt.title("Vessel Traffic Heatmap")
    plt.savefig("heatmap.png")
    plt.close()