"""Synthetic Baltic fleet for the local showcase; no observed vessel data."""
from datetime import datetime, timedelta, timezone
from math import cos, radians, sin

FLEET = (
    (211234000, 55.10, 18.20, 8.0, 45.0, 80),
    (219876000, 56.30, 20.40, 15.2, 270.0, 30),
    (230001000, 59.92, 24.75, 12.5, 95.0, 70),
    (265111000, 58.55, 17.05, 0.0, 0.0, 60),
)


def sample_rows():
    """Return an explicitly synthetic snapshot with relative UTC timestamps."""
    timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)
    rows = []
    for vessel_id, lat, lon, speed, course, ship_type in FLEET:
        distance = speed * 0.51444 * 1800
        moving = speed >= 0.5
        rows.append({
            'vessel_id': vessel_id, 'current_latitude': lat,
            'current_longitude': lon, 'current_timestamp': timestamp,
            'sog': speed, 'cog': course, 'heading': course,
            'pos_acc': True, 'nav_stat': 0 if moving else 1,
            'raw_json': {'properties': {'shipType': ship_type}},
            'predicted_latitude': lat + distance * cos(radians(course)) / 111111 if moving else None,
            'predicted_longitude': lon + distance * sin(radians(course)) / (111111 * cos(radians(lat))) if moving else None,
            'prediction_for_timestamp': timestamp + timedelta(minutes=30) if moving else None,
            'prediction_made_at': timestamp if moving else None,
        })
    return rows
