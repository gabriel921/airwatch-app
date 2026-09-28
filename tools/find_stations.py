import requests
import os
import json

with open("local.settings.json") as f:
    settings = json.load(f)
API_KEY = settings["Values"]["OPENAQ_API_KEY"]

cities = {
    "Lisbon": (38.7223, -9.1393),
    "London": (51.5074, -0.1278),
    "Paris": (48.8566, 2.3522),
    "New York": (40.7128, -74.0060),
    "Los Angeles": (34.0522, -118.2437),
    "Sao Paulo": (-23.5505, -46.6333),
    "Cairo": (30.0444, 31.2357),
    "Delhi": (28.6139, 77.2090),
    "Beijing": (39.9042, 116.4074),
    "Tokyo": (35.6762, 139.6503),
    "Sydney": (-33.8688, 151.2093),
    "Nairobi": (-1.2921, 36.8219),
}

headers = {"X-API-Key": API_KEY}

for city, (lat, lon) in cities.items():
    url = "https://api.openaq.org/v3/locations"
    params = {"coordinates": f"{lat},{lon}", "radius": 25000, "limit": 3}
    resp = requests.get(url, headers=headers, params=params)
    print(f"\n=== {city} ===")
    if resp.status_code == 200:
        for loc in resp.json().get("results", []):
            print(f"  id={loc['id']}  name={loc['name']}")
    else:
        print(f"  Error {resp.status_code}: {resp.text}")