import requests
import json

API_KEY = "OPENAQ_API_KEY"  # same one from local.settings.json
headers = {"X-API-Key": API_KEY}

stations_to_check = {
    "London": 141,
    "Los Angeles": 1019,
    "Sao Paulo": 5233,
    "Cairo": 1621200,
    "Delhi": 13,
    "Beijing": 21,
    "Sydney": 336,
    "Nairobi": 5994,
}

for city, openaq_id in stations_to_check.items():
    print(f"\n{'='*50}")
    print(f"{city} (openaq_id={openaq_id})")
    print('='*50)

    loc_resp = requests.get(f"https://api.openaq.org/v3/locations/{openaq_id}", headers=headers)
    if loc_resp.status_code != 200:
        print(f"  Location fetch failed: {loc_resp.status_code}")
        continue

    location_data = loc_resp.json()["results"][0]
    sensors_by_id = {s["id"]: s for s in location_data.get("sensors", [])}
    print(f"  Location name: {location_data.get('name')}")
    print(f"  Sensor count: {len(sensors_by_id)}")

    latest_resp = requests.get(f"https://api.openaq.org/v3/locations/{openaq_id}/latest", headers=headers)
    if latest_resp.status_code != 200:
        print(f"  Latest fetch failed: {latest_resp.status_code}")
        continue

    results = latest_resp.json().get("results", [])
    print(f"  Latest readings returned: {len(results)}")

    if not results:
        print("  --> No readings at all from /latest endpoint")

    for reading in results:
        sensor_id = reading.get("sensorsId")
        sensor = sensors_by_id.get(sensor_id, {})
        parameter = sensor.get("parameter", {}).get("name", "unknown")
        unit = sensor.get("parameter", {}).get("units", "?")
        value = reading.get("value")
        measured_at = reading.get("datetime", {}).get("utc")
        print(f"    {parameter:12} value={value:<10} unit={unit:<8} measured_at={measured_at}")