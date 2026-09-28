import requests

API_KEY = "OPENAQ_API_KEY"

headers = {
    "X-API-Key": API_KEY
}

cities = {
    "London": (51.5074, -0.1278),
    "Los Angeles": (34.0522, -118.2437),
    "Sao Paulo": (-23.5505, -46.6333),
    "Cairo": (30.0444, 31.2357),
    "Delhi": (28.6139, 77.2090),
    "Beijing": (39.9042, 116.4074),
    "Sydney": (-33.8688, 151.2093),
    "Nairobi": (-1.2864, 36.8172),
}

url = "https://api.openaq.org/v3/locations"

for city, (lat, lon) in cities.items():

    print(f"\n{'=' * 50}")
    print(city)
    print(f"{'=' * 50}")

    params = {
        "coordinates": f"{lat},{lon}",
        "radius": 25000,
        "limit": 10,
        "order_by": "id",
        "sort_order": "asc",
    }

    resp = requests.get(
        url,
        headers=headers,
        params=params
    )

    if resp.status_code != 200:
        print(f"  Search failed: {resp.status_code}")
        print(f"  Response: {resp.text}")
        continue

    data = resp.json()

    for loc in data.get("results", []):

        last = loc.get("datetimeLast")
        last_utc = last.get("utc") if last else None

        params_available = [
            sensor.get("parameter", {}).get("name")
            for sensor in loc.get("sensors", [])
        ]

        print(
            f"  id={loc['id']:<10} "
            f"name={loc.get('name', ''):<35} "
            f"last_reported={last_utc} "
            f"params={params_available}"
        )

        #Other Bot