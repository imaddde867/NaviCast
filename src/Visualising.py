import folium  

# Create a map centered on the Baltic Sea  
m = folium.Map(location=[60.1282, 18.6435], zoom_start=8)  

# Add a marker for a vessel  
folium.Marker(  
    [60.1, 18.6],  
    popup="Vessel 123",  
    icon=folium.Icon(color="blue")  
).add_to(m)  

# Save the map  
m.save("map.html")  