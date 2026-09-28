import azure.functions as func
import logging
import os
import json
import requests
import mssql_python
from datetime import datetime, timezone, timedelta

logging.getLogger("azure").setLevel(logging.WARNING)

app = func.FunctionApp()

# (OpenAQ location ID, friendly city name)
STATIONS = [
    (7199, "Lisbon"),
    (151, "London"), 
    (2681, "Paris"), 
    (384, "New York"),
    (7936, "Los Angeles"), 
    (5243, "Sao Paulo"), 
    (1621200, "Cairo"),
    (235, "Delhi"), 
    (8833, "Beijing"), 
    (1214487, "Tokyo"),
    (1544061, "Sydney"), 
    (5199863, "Nairobi"),
]

def get_db_connection():
    server = os.environ["SQL_SERVER"]
    database = os.environ["SQL_DATABASE"]
    conn_str = (
        f"Server={server};"
        f"Database={database};"
        f"Authentication=ActiveDirectoryDefault;"
        f"Encrypt=yes;"
    )
    return mssql_python.connect(conn_str)


def ensure_station_exists(cursor, openaq_id, friendly_name, location_data):
    """Insert the station only the first time we see it. Returns our internal station_id."""
    cursor.execute("SELECT station_id FROM stations WHERE openaq_id = ?", openaq_id)
    row = cursor.fetchone()
    if row:
        return row[0]

    station_name = location_data.get("name", "Unknown")
    country = (location_data.get("country") or {}).get("name")
    coords = location_data.get("coordinates") or {}
    lat = coords.get("latitude")
    lon = coords.get("longitude")

    cursor.execute(
        """
        INSERT INTO stations (openaq_id, name, city, country, latitude, longitude, last_updated)
        OUTPUT INSERTED.station_id
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        openaq_id, station_name, friendly_name, country, lat, lon, datetime.now(timezone.utc)
    )
    return cursor.fetchone()[0]



def fetch_and_insert(cursor, openaq_id, friendly_name, headers):
    loc_resp = requests.get(f"https://api.openaq.org/v3/locations/{openaq_id}", headers=headers)
    if loc_resp.status_code != 200:
        logging.warning(f"Failed to fetch location {friendly_name}: {loc_resp.status_code}")
        return 0
    location_data = loc_resp.json()["results"][0]

    station_id = ensure_station_exists(cursor, openaq_id, friendly_name, location_data)

    latest_resp = requests.get(f"https://api.openaq.org/v3/locations/{openaq_id}/latest", headers=headers)
    if latest_resp.status_code != 200:
        logging.warning(f"Failed to fetch latest for {friendly_name}: {latest_resp.status_code}")
        return 0

    results = latest_resp.json().get("results", [])
    sensors_by_id = {s["id"]: s for s in location_data.get("sensors", [])}

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    inserted = 0
    skipped_stale = 0
    skipped_unit = 0

    for reading in results:
        sensor_id = reading.get("sensorsId")
        sensor = sensors_by_id.get(sensor_id, {})
        parameter = sensor.get("parameter", {}).get("name", "unknown")
        unit = sensor.get("parameter", {}).get("units", "")
        value = reading.get("value")
        measured_at_str = reading.get("datetime", {}).get("utc")

        if value is None or measured_at_str is None or value < 0:
            continue

        # Skip non-metric units so cross-station comparisons stay meaningful
        if unit != "µg/m³":
            skipped_unit += 1
            continue

        # Skip stale sensor data (sensor hasn't reported in 48+ hours)
        measured_at = datetime.fromisoformat(measured_at_str.replace("Z", "+00:00"))
        if measured_at < cutoff:
            skipped_stale += 1
            continue

        cursor.execute(
            """
            INSERT INTO readings (station_id, parameter, value, unit, measured_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            station_id, parameter, value, unit, measured_at_str
        )
        inserted += 1

    if skipped_stale or skipped_unit:
        logging.info(f"{friendly_name}: skipped {skipped_stale} stale, {skipped_unit} non-metric")

    return inserted

@app.timer_trigger(schedule="0 0 0 * * *", arg_name="mytimer", run_on_startup=False)
def ingest_air_quality(mytimer: func.TimerRequest) -> None:
    logging.info("AirWatch ingestion function triggered.")

    headers = {"X-API-Key": os.environ["OPENAQ_API_KEY"]}
    conn = get_db_connection()
    cursor = conn.cursor()

    total_inserted = 0
    for openaq_id, friendly_name in STATIONS:
        try:
            count = fetch_and_insert(cursor, openaq_id, friendly_name, headers)
            total_inserted += count
            logging.info(f"{friendly_name}: inserted {count} readings")
        except Exception as e:
            logging.error(f"Error processing {friendly_name}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    logging.info(f"Ingestion run complete. Total readings inserted: {total_inserted}")

@app.route(route="air-quality", auth_level=func.AuthLevel.ANONYMOUS)
def get_air_quality(req: func.HttpRequest) -> func.HttpResponse:
    conn = get_db_connection()
    cursor = conn.cursor()

    city_filter = req.params.get("city")

    if city_filter:
        cursor.execute(
            "SELECT city, parameter, reading_date, avg_value, unit, reading_count FROM daily_averages WHERE city = ? ORDER BY reading_date DESC",
            city_filter
        )
    else:
        cursor.execute(
            "SELECT city, parameter, reading_date, avg_value, unit, reading_count FROM daily_averages ORDER BY city, parameter, reading_date DESC"
        )

    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    for row in rows:
        if hasattr(row["reading_date"], "isoformat"):
            row["reading_date"] = row["reading_date"].isoformat()

    cursor.close()
    conn.close()

    return func.HttpResponse(
        json.dumps(rows, default=str),
        mimetype="application/json",
        status_code=200
    )

