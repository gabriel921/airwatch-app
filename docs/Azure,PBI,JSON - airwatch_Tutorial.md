# AirWatch — Build It Yourself, From Scratch

A step-by-step tutorial for building a real-time air quality monitoring pipeline using OpenAQ, Azure Functions, Azure SQL Database, and Power BI — entirely on free-tier Azure services.

**What you'll build:**
- A Python Azure Function that pulls live air quality data once a day
- An Azure SQL Database storing that data
- A second Python Azure Function exposing the data as a JSON API
- A Power BI dashboard published to the web as a live demo
- Everything running continuously at $0/month (GitHub Actions is optional, not required)

**Stack decisions made for this build:**
- Language: Python (for both Azure Functions)
- Auth to database: Managed Identity (no passwords/secrets in code)
- Cost model: fully free tier — Azure SQL free offer (100,000 vCore-seconds/month, auto-pause enabled) + Azure Functions Consumption plan (1M free executions/month)

---

## ⚠️ READ THIS FIRST: Understanding Azure Costs (Important!)

If you're new to Azure, this section matters more than any single technical step. Read it before you create anything.

**Two different "free" things exist, and they're easy to confuse:**

1. **The 30-day Free Trial** — when you first sign up, Azure gives you a **€200 credit** that lasts **30 days**, no matter how much or little you actually use. This is a sandbox, not a long-term home for a project.
2. **Always-free service tiers** — separately, certain services (like Azure SQL's free offer and Azure Functions' Consumption plan) have generous monthly quotas that renew forever, at €0, for the life of your account.

**The catch:** the always-free tiers only work indefinitely once you're on a **Pay-As-You-Go (PAYG)** subscription. On the initial 30-day Free Trial, everything — even the "always free" stuff — gets **disabled** after 30 days unless you upgrade to PAYG. There's usually a ~30-day grace period where nothing is deleted yet, but the project stops running.

**Do the numbers actually work out free forever on PAYG?** Yes, comfortably, for a project this size:
- **Storage**: ~50 stations reporting every 30 min works out to roughly 20–35 MB of data per month. Against the 32 GB free storage limit, that's over **80 years** before you'd ever fill it.
- **Compute**: the database only "spends" its free 100,000 vCore-seconds/month while actively handling a query (it auto-pauses in between). Realistic usage here lands around 10,000–15,000 vCore-seconds/month — well under the limit.
- **Function executions**: ~1,440 ingestion runs/month against a 1,000,000/month free allowance.

So: upgrading to PAYG does **not** mean you'll get charged. It just removes the 30-day training-wheels ceiling and lets the real always-free quotas apply permanently. You will not be charged unless you both (a) are on PAYG and (b) exceed the free monthly quotas — which, per the math above, is extremely unlikely for a portfolio-sized project.

**The safety net — set this up regardless of trial or PAYG:**
1. Search **"Cost Management + Billing"** in the portal → **Budgets** (Portuguese: "Orçamentos") → **+ Add**.
2. Scope: your subscription. Amount: **€1/month**.
3. Add two alert thresholds, both set to **"Actual"** (not "Forecasted"): 80% (€0.80) and 100% (€1.00), notifying your email.
4. This means if anything ever genuinely starts costing money, you get an email warning almost immediately — long before it becomes a real bill.

**When to actually upgrade to PAYG:** not on day one. Do all the free-tier learning/building during the 30-day trial window. Only upgrade once the project is built and you've decided you want it to be a permanent, always-on live demo (see the final section of this tutorial for exactly how to upgrade, and how to tear everything down instead if you'd rather not keep it running).

---

## Step 1: Create a Free Azure Account

1. Go to **azure.microsoft.com/free** and click **Start free**.
2. Sign in with a Microsoft account (or create one — any email works).
3. You'll be asked for identity verification (phone number) and a credit card for verification purposes only — Azure will not charge you unless you explicitly upgrade to a paid subscription later. The free trial gives you $200 of credit for 30 days, but we won't need to touch that credit at all since everything in this build uses always-free tiers.
4. Once your account is created, you'll land on the **Azure Portal** at portal.azure.com.

## Step 2: Create a Resource Group

A resource group is just a folder that holds all the Azure resources for this project together, so you can manage or delete them as one unit.

1. In the Azure Portal search bar at the top, type **Resource groups** and click it.
2. Click **+ Create**.
3. Fill in:
   - **Subscription**: your free subscription (should be the only option)
   - **Resource group name**: `airwatch-rg`
   - **Region**: pick the region closest to you (e.g., West Europe if you're in Portugal)
4. Click **Review + create**, then **Create**.
5. Wait for the "Deployment succeeded" notification.

You now have an empty container ready to hold the database and Functions we'll create in the next steps.

## Step 3: Create the Azure SQL Database (serverless, free tier)

1. In the top search bar, type **"SQL databases"** and click it.
2. Click **+ Create**.
3. On the **Basics** tab, you should immediately see a panel confirming **"Free offer applied"** — 100,000 vCore-seconds, 32 GB of data, 32 GB of backup storage free per month, for the lifetime of your subscription. Overage billing is disabled by default, meaning if you ever hit the free limit the database simply auto-pauses until next month rather than charging you. No changes needed here.
4. Fill in **Project details**:
   - Subscription: your free subscription
   - Resource group: `airwatch-rg`
5. Fill in **Database details**:
   - Database name: `airwatch-db`
   - Server: click **Create new**
     - Server name: something globally unique (e.g. `airwatch-server-yourname`)
     - **Location**: pick a nearby region. ⚠️ **Known issue**: some regions periodically stop accepting new subscriptions ("The selected region is currently not accepting new customers"). If your first choice (e.g. West Europe) fails with this error, just try another nearby region — **North Europe** or **Sweden Central** are good fallbacks and usually open.
     - Authentication method: **"Use Microsoft Entra-only authentication"** — this is what lets us skip SQL passwords entirely later and use Managed Identity
     - Set yourself as the Microsoft Entra admin
     - Click **OK**
6. Under **Networking**:
   - Connectivity method: Public endpoint
   - Allow Azure services and resources to access this server: **Yes**
   - Add current client IP address: **Yes**
7. Click **Review + create** → **Create**. Deployment takes a few minutes.
   - ⚠️ **Known issue**: even after successful deployment, the free trial's cost estimate ("€200 free credit") can show a small deduction shortly after setup — this is usually leftover billing from a failed deployment attempt in a disallowed region, not an ongoing charge. Check **Cost Management + Billing → Cost analysis → Cost by resource** if you want to confirm nothing is actively billing you.

## Step 4: Open the Query Editor

1. Go to your resource group → click on **airwatch-db** (the database, not the server).
2. In the left sidebar, find **Query editor (preview)** (Portuguese portal: "Editor de consultas (versão prévia)", usually under "Definições").
3. Sign in using Microsoft Entra authentication (your own account — no password, since we set up Entra-only auth).
4. If you get a connection error like *"Database is not currently available"* — the serverless database has likely auto-paused from inactivity. Wait ~30-60 seconds and retry; the first connection triggers it to resume. If it persists, check the server's firewall rules and add your current client IP.

## Step 5: Design and Create the Schema

We're storing two kinds of things: **monitoring stations** (where readings come from) and **readings** (the actual pollutant measurements). These go in two separate, linked tables rather than one big table — this is called **normalization**.

**Why split them?** If station info (name, city, coordinates) were repeated in every single reading row, you'd waste storage repeating identical data thousands of times, and worse, if a station's name ever needed correcting, you'd have to update every single row instead of one.

### `stations` table

```sql
CREATE TABLE stations (
    station_id INT IDENTITY(1,1) PRIMARY KEY,
    openaq_id INT NOT NULL UNIQUE,
    name NVARCHAR(200) NOT NULL,
    city NVARCHAR(100) NULL,
    country NVARCHAR(100) NULL,
    latitude DECIMAL(9,6) NULL,
    longitude DECIMAL(9,6) NULL,
    last_updated DATETIME2 NULL
);
```

- `station_id INT IDENTITY(1,1) PRIMARY KEY` — our own auto-incrementing internal ID, uniquely identifies each row.
- `openaq_id INT NOT NULL UNIQUE` — OpenAQ's own ID for the station, used to match incoming API data to the right row.
- `NVARCHAR` instead of `VARCHAR` — supports international characters (accents, non-Latin scripts), since station names come from cities worldwide.
- `DECIMAL(9,6)` for lat/lon — exact precision (no floating-point rounding), 6 decimal places ≈ 10cm precision.

### `readings` table

```sql
CREATE TABLE readings (
    reading_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    station_id INT NOT NULL,
    parameter NVARCHAR(20) NOT NULL,
    value DECIMAL(10,3) NOT NULL,
    unit NVARCHAR(20) NOT NULL,
    measured_at DATETIME2 NOT NULL,
    ingested_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_readings_stations FOREIGN KEY (station_id) REFERENCES stations(station_id)
);
```

- `reading_id BIGINT` — a separate auto-incrementing key rather than reusing `(station_id, measured_at)`, because a single station reports multiple pollutants at the same timestamp (PM2.5, NO2, O3 all at 10:00 AM), which would violate a composite primary key's uniqueness rule. `BIGINT` (not `INT`) because this table will grow into the millions of rows over time.
- `FOREIGN KEY (station_id) REFERENCES stations(station_id)` — enforces that every reading must point to a real, existing station. SQL Server will reject any insert that references a non-existent station, preventing orphaned data. This is **referential integrity**.
- Two separate timestamps: `measured_at` (when the sensor took the reading, from OpenAQ) vs `ingested_at` (when our system pulled it in, defaults to `SYSUTCDATETIME()`) — useful for debugging lag later.

### Verify it works

Insert a station and a valid reading:
```sql
INSERT INTO stations (openaq_id, name, city, country, latitude, longitude)
VALUES (12345, 'Lisbon Test Station', 'Lisbon', 'Portugal', 38.7223, -9.1393);

INSERT INTO readings (station_id, parameter, value, unit, measured_at)
VALUES (1, 'pm25', 12.500, 'µg/m³', '2026-09-02 10:00:00');
```

Try inserting a reading for a station that doesn't exist (should fail):
```sql
INSERT INTO readings (station_id, parameter, value, unit, measured_at)
VALUES (999, 'pm25', 15.000, 'µg/m³', '2026-09-02 10:00:00');
```
This correctly errors with a `FOREIGN KEY constraint` conflict — proof the relationship is enforced.

Join the two tables together:
```sql
SELECT r.reading_id, s.name AS station_name, s.city, r.parameter, r.value, r.unit, r.measured_at
FROM readings r
JOIN stations s ON r.station_id = s.station_id;
```

> **Note**: SQL editors typically run the *entire* pane unless you highlight specific lines. If you get "already an object named X" errors, either open a new query tab or select only the statements you want to run before executing.

## Step 6: Local Development Environment (Windows)

1. **Check your Python version**:
   ```
   python --version
   ```
   Azure Functions currently supports Python **3.10–3.13** (3.13 recommended for new projects). If your system default is newer (e.g. 3.14), don't uninstall it — just install 3.13 alongside it. Download from python.org, and make sure **"Add python.exe to PATH"** is checked during install. Restart your terminal afterward, then confirm with:
   ```
   py -0
   ```
   This lists every Python version installed side by side.

2. **Create a project folder + virtual environment**, following the same layout as your other portfolio projects:
   ```
   mkdir airwatch-app
   cd airwatch-app
   py -3.13 -m venv .venv
   .venv\Scripts\activate
   python --version
   ```
   The venv keeps this project's dependencies fully isolated from your other projects. You should see `(.venv)` at the start of your terminal prompt once activated, and `python --version` should report 3.13.x.

3. **Install Azure Functions Core Tools** (lets you build/run/test Functions locally):
   ```
   winget install Microsoft.Azure.FunctionsCoreTools
   ```

4. **Install the Azure CLI** (lets you log in and deploy from the terminal):
   ```
   winget install Microsoft.AzureCLI
   ```
   After both installs finish, fully close and reopen VS Code so it picks up the new PATH entries. Then verify:
   ```
   func --version
   az --version
   ```

5. **Install two VS Code extensions** (Ctrl+Shift+X to open the Extensions panel):
   - **Azure Functions** (Microsoft)
   - **Azure Account** (Microsoft)

6. **Log into Azure from the terminal**:
   ```
   az login
   ```
   ⚠️ **Known issue — MFA / Security Defaults error (AADSTS50076 or AADSTS530035)**: personal Microsoft accounts on Azure often have "Security Defaults" enabled, which requires a fresh MFA-verified sign-in. Plain `az login` or `az login --use-device-code` can sometimes fail this even though logging into the portal directly works fine. Fix: log in with your **tenant ID** explicitly, which forces a proper fresh interactive browser sign-in:
   ```
   az login --tenant YOUR_TENANT_ID
   ```
   **How to find your tenant ID**: in the Azure Portal, search **"Microsoft Entra ID"** → the **Overview** page shows it at the top. Alternatively, run `az account show` after any successful login, or look for it embedded in the error message text itself if a login attempt fails (Azure includes it there too).

   Once logged in, you'll see a list of your subscriptions — press **Enter** to accept the default (should be marked with a `*`).

## Step 7: The Ingestion Function (OpenAQ → Azure SQL)

### Get a free OpenAQ API key

OpenAQ now requires an API key on every request (sent via the `X-API-Key` header).

1. Register at **explore.openaq.org/register** (free, just an email).
2. Verify your email if asked.
3. Go to **explore.openaq.org/account** and copy your API key.

This key is a secret, same as a password — it never goes directly into code that could reach GitHub.

### Initialize the Function project

In your project folder (venv active):
```
func init . --python
```
This scaffolds `function_app.py`, `host.json`, `local.settings.json`, `requirements.txt`, `.funcignore`.

### Store secrets locally

Open `local.settings.json` and add your key plus the DB connection details inside `"Values"`:
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "OPENAQ_API_KEY": "your-actual-key-here",
    "SQL_SERVER": "your-server-name.database.windows.net",
    "SQL_DATABASE": "airwatch-db"
  }
}
```
Confirm `local.settings.json` is listed in `.gitignore` (it is by default from `func init`) — this file must never be committed.

### Install dependencies

```
pip install azure-functions azure-identity pyodbc requests
pip freeze > requirements.txt
```

`pyodbc` needs a system-level ODBC driver too (not just the Python package). Check what's installed with (run in a plain PowerShell window, not the venv):
```
Get-OdbcDriver | Where-Object Name -like "*SQL Server*"
```
**ODBC Driver 17 for SQL Server** or newer works fine.

### Find real OpenAQ station IDs

Don't guess station IDs — query OpenAQ directly. Create `find_stations.py`:
```python
import requests
import json

with open("local.settings.json") as f:
    settings = json.load(f)
API_KEY = settings["Values"]["OPENAQ_API_KEY"]

cities = {
    "Lisbon": (38.7223, -9.1393), "London": (51.5074, -0.1278),
    "Paris": (48.8566, 2.3522), "New York": (40.7128, -74.0060),
    "Los Angeles": (34.0522, -118.2437), "Sao Paulo": (-23.5505, -46.6333),
    "Cairo": (30.0444, 31.2357), "Delhi": (28.6139, 77.2090),
    "Beijing": (39.9042, 116.4074), "Tokyo": (35.6762, 139.6503),
    "Sydney": (-33.8688, 151.2093), "Nairobi": (-1.2921, 36.8219),
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
```
Run with `python find_stations.py`. Reading the key from `local.settings.json` (instead of hardcoding it) means this utility script stays safe to commit later.

**Stations picked for this build** (one per city, 25km search radius):

| City | OpenAQ ID | Station name |
|---|---|---|
| Lisbon | 7199 | Restelo |
| London | 141 | London Harlington |
| Paris | 2681 | Place de l'Opéra |
| New York | 384 | CCNY |
| Los Angeles | 1019 | Pasadena |
| São Paulo | 5233 | Cid. Universitária-USP-Ipen |
| Cairo | 1621200 | Cairo |
| Delhi | 13 | Delhi Technological University |
| Beijing | 21 | Beijing US Embassy |
| Tokyo | 1214487 | Mitaka |
| Sydney | 336 | Earlwood |
| Nairobi | 5994 | Nairobi CBD |

**⚠️ Update: 8 of these 12 stations turned out to be dead.** See "Diagnosing and Fixing Dead Stations" further down — the IDs above were the *initial* picks (closest station to each city), but several pointed at archived/dormant OpenAQ records that stopped reporting years ago. The final, working IDs are in that section.

### The ingestion function code

Replace `function_app.py` with:

```python
import azure.functions as func
import logging
import os
import json
import requests
import pyodbc
from azure.identity import DefaultAzureCredential
from datetime import datetime, timezone

app = func.FunctionApp()

# (OpenAQ location ID, friendly city name)
STATIONS = [
    (7199, "Lisbon"), (141, "London"), (2681, "Paris"), (384, "New York"),
    (1019, "Los Angeles"), (5233, "Sao Paulo"), (1621200, "Cairo"),
    (13, "Delhi"), (21, "Beijing"), (1214487, "Tokyo"),
    (336, "Sydney"), (5994, "Nairobi"),
]


def get_db_connection():
    """Connect using Azure AD identity (local az login, or the Function's
    Managed Identity once deployed) instead of a password."""
    server = os.environ["SQL_SERVER"]
    database = os.environ["SQL_DATABASE"]

    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")
    token_bytes = token.token.encode("utf-16-le")
    exp_token = b'\x01' + len(token_bytes).to_bytes(4, 'little') + token_bytes

    conn_str = (
        f"Driver={{ODBC Driver 17 for SQL Server}};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
    )
    SQL_COPT_SS_ACCESS_TOKEN = 1256
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: exp_token})


def ensure_station_exists(cursor, openaq_id, location_data):
    """Insert the station only the first time we see it. Returns our internal station_id."""
    cursor.execute("SELECT station_id FROM stations WHERE openaq_id = ?", openaq_id)
    row = cursor.fetchone()
    if row:
        return row[0]

    name = location_data.get("name", "Unknown")
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
        openaq_id, name, name, country, lat, lon, datetime.now(timezone.utc)
    )
    return cursor.fetchone()[0]


def fetch_and_insert(cursor, openaq_id, friendly_name, headers):
    loc_resp = requests.get(f"https://api.openaq.org/v3/locations/{openaq_id}", headers=headers)
    if loc_resp.status_code != 200:
        logging.warning(f"Failed to fetch location {friendly_name}: {loc_resp.status_code}")
        return 0
    location_data = loc_resp.json()["results"][0]

    station_id = ensure_station_exists(cursor, openaq_id, location_data)

    latest_resp = requests.get(f"https://api.openaq.org/v3/locations/{openaq_id}/latest", headers=headers)
    if latest_resp.status_code != 200:
        logging.warning(f"Failed to fetch latest for {friendly_name}: {latest_resp.status_code}")
        return 0

    results = latest_resp.json().get("results", [])
    sensors_by_id = {s["id"]: s for s in location_data.get("sensors", [])}

    inserted = 0
    for reading in results:
        sensor_id = reading.get("sensorsId")
        sensor = sensors_by_id.get(sensor_id, {})
        parameter = sensor.get("parameter", {}).get("name", "unknown")
        unit = sensor.get("parameter", {}).get("units", "")
        value = reading.get("value")
        measured_at = reading.get("datetime", {}).get("utc")

        if value is None or measured_at is None:
            continue

        cursor.execute(
            """
            INSERT INTO readings (station_id, parameter, value, unit, measured_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            station_id, parameter, value, unit, measured_at
        )
        inserted += 1

    return inserted


@app.timer_trigger(schedule="0 */30 * * * *", arg_name="mytimer", run_on_startup=False)
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
```

**What each piece is doing:**
- `get_db_connection()` — no password anywhere. It asks Azure for a short-lived access token proving your identity (locally, your `az login` session; once deployed, the Function App's own Managed Identity), and hands that token to the SQL driver instead of a password.
- `ensure_station_exists()` — checks by `openaq_id` first so we never insert the same station twice; the row is created once, then reused on every run.
- `fetch_and_insert()` — two OpenAQ calls per station: one for metadata (name, coordinates, sensor list), one for the actual latest measured values.
- The `try/except` around each station in the main loop means one station failing (timeout, bad data) doesn't kill the whole run — the others still get processed.

### Test it locally before deploying

The timer trigger needs a storage backend to track its schedule — locally we fake this with **Azurite** (Azure Storage emulator), rather than needing a real Azure Storage Account yet.

1. Install Node.js from **nodejs.org** (LTS version) if you don't have it — Azurite needs it. Fully restart VS Code after installing so PATH updates register.
2. Install Azurite:
   ```
   npm install -g azurite
   ```
3. In `local.settings.json`, set:
   ```json
   "AzureWebJobsStorage": "UseDevelopmentStorage=true"
   ```
4. Temporarily change the timer trigger to fire immediately instead of waiting up to 30 minutes — in `function_app.py`:
   ```python
   @app.timer_trigger(schedule="0 */30 * * * *", arg_name="mytimer", run_on_startup=True)
   ```
   (Revert `run_on_startup` back to `False` before deploying to Azure — otherwise it fires on every cold start/restart in production, not just on schedule.)
5. Open **two terminals** in the project folder:
   - Terminal 1 — start the emulator, leave running: `azurite`
   - Terminal 2 (venv active) — start the function: `func start`

Watch Terminal 2 for log lines like `Lisbon: inserted X readings` for each of the 12 stations, and a final `Ingestion run complete` summary.

### Fixing real bugs found from live data

Running against real data surfaced three issues worth fixing before moving on — this is a normal part of building a pipeline, not a sign anything was wrong with the design:

1. **`city` column bug**: `ensure_station_exists` was inserting the station's own `name` into both the `name` and `city` columns. Fix: pass the friendly city name (from our `STATIONS` list) as a separate parameter and store it correctly.
2. **Stale data**: OpenAQ's `/latest` endpoint returns the last known value for *every* sensor at a station, even ones that stopped reporting years ago (we saw readings from 2016–2019 mixed in with today's data). Fix: skip any reading older than a cutoff window before inserting.
3. **Mixed units**: some sensors report `µg/m³`, others `ppm` for the same pollutant, which breaks cross-station comparison. Fix: only keep `µg/m³` readings.

Updated `ensure_station_exists` and `fetch_and_insert`:

```python
from datetime import datetime, timezone, timedelta

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

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)  # widened from 48h — many stations report on longer cycles
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

        if value is None or measured_at_str is None:
            continue

        if unit != "µg/m³":
            skipped_unit += 1
            continue

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
```

**Housekeeping**: after changing the logic, clear out old test/bad data before rerunning:
```sql
DELETE FROM readings;
DELETE FROM stations;
```

### Diagnosing and fixing dead stations

After widening the cutoff to 7 days, 8 of the 12 cities still returned **zero** readings. Widening the cutoff further didn't help — a diagnostic script hitting each station's `/latest` endpoint directly (no filtering at all) showed why: several of the original station IDs pointed at real but **dormant** OpenAQ records — stations that physically stopped reporting years ago (some as far back as 2016–2018). No cutoff window fixes a station that simply isn't live anymore; the fix has to be swapping in currently-active stations.

**Finding active replacements**: OpenAQ's `/v3/locations` search endpoint accepts `order_by=datetimeLast&sort_order=desc`, which ranks nearby stations by how recently they last reported — exactly what's needed to pick a live one within a city's search radius.

**Final, working station list** (replaces the initial picks above):

| City | Old ID (dead) | New ID (active) | Station name | Last reported before fix |
|---|---|---|---|---|
| London | 141 | **151** | Tower Hamlets - Mile End Road | same-day |
| Los Angeles | 1019 | **7936** | Los Angeles - N. Main | same-day |
| São Paulo | 5233 | **5243** | Pinheiros | 2023-04 *(no fresher option exists in this region)* |
| Cairo | 1621200 | **1621200** | Cairo | unchanged — only station available |
| Delhi | 13 | **235** | Anand Vihar, New Delhi - DPCC | ~daily |
| Beijing | 21 | **8833** | Beijing | 2025-03 *(no fresher option exists)* |
| Sydney | 336 | **1544061** | Anzac Memorial | same-day |
| Nairobi | 5994 | **5199863** | Kihumo Village \|\| Antenna Array | same-day |

Lisbon, Paris, New York, and Tokyo kept their original IDs — those were already active.

```python
# (OpenAQ location ID, friendly city name)
STATIONS = [
    (7199, "Lisbon"), (151, "London"), (2681, "Paris"), (384, "New York"),
    (7936, "Los Angeles"), (5243, "Sao Paulo"), (1621200, "Cairo"),
    (235, "Delhi"), (8833, "Beijing"), (1214487, "Tokyo"),
    (1544061, "Sydney"), (5199863, "Nairobi"),
]
```

**Known, accepted gap**: São Paulo and Cairo still return 0 readings even with the live stations — that's the genuine extent of OpenAQ's current coverage for those regions, not a bug. The dashboard will honestly show "no recent data" for these two, which is reasonable behavior for a real air-quality tool rather than something to hide.

**Two side effects worth knowing**, not bugs:
- Some busier replacement stations (e.g. Los Angeles) report several `ppm`-unit pollutants (co, no, nox) alongside the `µg/m³` ones we want — these get correctly filtered out by the existing unit check, showing up as a higher `non-metric` skip count in the logs.
- The Sydney and Nairobi replacements are low-cost sensor stations (PurpleAir-style), not government reference monitors — their `pm25` values are still in µg/m³ and flow through fine, but the underlying data quality is a notch below a reference station. Fine for a portfolio demo, worth knowing if asked.

After updating `STATIONS`, clear old data and rerun:
```sql
DELETE FROM readings;
DELETE FROM stations;
```

### Building the daily-average view

`readings` holds raw, per-sensor measurements — exactly what ingestion needs, but the wrong shape for a dashboard. Power BI and the future API want one summary number per city, per pollutant, per day, not every individual reading. A SQL **view** is a saved query that behaves like a virtual table, recalculating from live data every time it's queried:

```sql
CREATE VIEW daily_averages AS
SELECT
    s.city,
    r.parameter,
    CAST(r.measured_at AS DATE) AS reading_date,
    AVG(r.value) AS avg_value,
    r.unit,
    COUNT(*) AS reading_count
FROM readings r
JOIN stations s ON s.station_id = r.station_id
GROUP BY s.city, r.parameter, CAST(r.measured_at AS DATE), r.unit;
```

- `CAST(r.measured_at AS DATE)` strips the time off a timestamp, leaving just the calendar date, which is what lets rows from different hours of the same day group together.
- Every non-aggregated column in `SELECT` must appear in `GROUP BY` — that's how SQL knows what defines "one group."
- `COUNT(*) AS reading_count` is a bonus transparency column — useful later for showing "based on N readings" in the dashboard.

Test it: `SELECT * FROM daily_averages ORDER BY city, parameter;`

### Bug: negative pollutant values slipping through

The view surfaced a real data-quality bug: one row showed `Lisbon, no2, -1.000000`. Negative pollutant concentrations are physically impossible — `-1` is almost certainly OpenAQ's sentinel value for a sensor error, not a real reading, and the existing `value is None` check didn't catch it because `-1` isn't `None`.

**Fix, at ingestion time** (not just in the view — keeping `readings` itself clean matters for anything built on it later):
```python
if value is None or measured_at_str is None or value < 0:
    continue
```

**A second, unrelated bug was hit while making this edit**: the code had been refactored at some point to rename the raw timestamp string to `measured_at_str` (keeping `measured_at` for the parsed `datetime` object, computed further down), but the null-check line still referenced the old name `measured_at` — which doesn't exist yet at that point in the function. This threw `cannot access local variable 'measured_at'` on every single station. Fix was purely using the correct variable name, `measured_at_str`, in the check above — the rest of the flow (unit filter → staleness parse/check → insert) was already correctly ordered.

After fixing both, a clean wipe-and-rerun produced correct data across all 10 live cities with no negative values.

**⚠️ Azurite gotcha**: Azurite is a long-running background server — running `azurite` in a terminal and seeing no further output is the *correct* state (it's listening silently), not a hang. It must be started in its own terminal, left running, before `func start` in a second terminal.

**⚠️ Known issue — recurring "database not currently available" / login timeout errors**: this happens any time the serverless database has been idle for a while (it auto-pauses). Fix is always the same: open the Query Editor in the portal, run `SELECT 1;` to force it awake, then retry `func start`. If that alone doesn't fix it, also check the server's Networking/firewall page — your IP may have changed and need re-adding.

---

## Step 10: Deploy the Ingestion Function to Azure

So far everything has run locally via Azurite. Now we create the real cloud home for it.

1. Portal → search **"Function App"** → Create.
2. **Hosting plan**: Flex Consumption (the newer serverless plan; has a generous permanent free monthly grant).
3. **Resource group**: `airwatch-rg`. **Name**: something globally unique, e.g. `airwatch-func-yourname`. **Runtime stack**: Python, version matching your local venv (e.g. 3.13). **Region**: same as your database. **OS**: Linux.
4. Instance size: default (e.g. 2048 MB) is fine — our workload is light and stays far under the free compute grant regardless.
5. Zone redundancy: **off** (adds cost, unnecessary for a portfolio project).
6. Let it auto-create a Storage Account on the Storage tab (defaults are fine) — this is required for the timer trigger to track its schedule, and is itself covered by a separate free tier.
7. Create. Takes a minute or two.

**Enable Managed Identity and grant database access:**
1. Function App → **Identidade** (Identity) → System assigned → On → Save. Note the Object ID it gives you.
2. In the SQL Query Editor for `airwatch-db`, run (replacing with your actual Function App name):
   ```sql
   CREATE USER [airwatch-func-yourname] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_datareader ADD MEMBER [airwatch-func-yourname];
   ALTER ROLE db_datawriter ADD MEMBER [airwatch-func-yourname];
   ```

**Set app settings** (the cloud equivalent of `local.settings.json`, which never gets deployed):
Function App → **Configuração**/**Variáveis de ambiente** → add:
- `OPENAQ_API_KEY`
- `SQL_SERVER` (e.g. `airwatch-server-yourname.database.windows.net`)
- `SQL_DATABASE` (`airwatch-db`)

**Deploy the code:**
1. Install the **Azure Functions** extension in VS Code, sign in to Azure from it.
2. Open your project folder as the active workspace (File → Open Folder).
3. Azure panel → right-click your Function App → **Deploy to Function App...** → select your project folder → confirm the overwrite.

## Step 11: Fix the ODBC driver problem (Linux Function Apps)

The first deployment will likely fail with an error like:
```
pyodbc.Error: [unixODBC][Driver Manager] Can't open lib 'ODBC Driver 17 for SQL Server' : file not found
```
This is a known gap: Azure's Linux Python Functions runtime doesn't ship the Microsoft ODBC driver that `pyodbc` needs, and the Flex Consumption plan doesn't support custom containers (which would otherwise let you install it yourself).

**Fix: switch from `pyodbc` to Microsoft's `mssql-python` package**, which bundles its own driver binaries directly in the pip install — no system-level driver needed.

`requirements.txt`:
```
azure-functions
mssql-python
requests
```

`function_app.py` — replace the whole `get_db_connection()` function with:
```python
import mssql_python

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
```
`ActiveDirectoryDefault` uses the same credential-chain logic as `DefaultAzureCredential` — it authenticates via `az login` locally and via Managed Identity once deployed, with no code branching between the two. Remove the now-unused `pyodbc`, `struct`, and `azure-identity` imports. Redeploy.

## Step 12: Build and Deploy the API Function

Add a second function to the same `function_app.py`, alongside `ingest_air_quality`:

```python
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
```
`auth_level=ANONYMOUS` means no API key is needed to call it — reasonable for public, non-sensitive air quality data. `?city=London` optionally filters.

Redeploy the same way as before. Your Function App's real public hostname includes a unique suffix Azure assigns (check **Descrição Geral** on the Function App for the exact URL) — it won't be the plain `<name>.azurewebsites.net` you might expect. The live endpoint is:
```
https://<your-actual-hostname>/api/air-quality
```

## Step 13: Avoiding a Real Cost Incident

This is worth doing proactively, not after the fact. A 30-minute ingestion schedule has a hidden problem: Azure SQL Serverless auto-pauses after ~1 hour of no activity, which is what keeps it free. A query every 30 minutes never lets it go idle long enough to pause — so it runs continuously, and can burn through the whole month's free compute allowance (100,000 vCore-seconds) in about a week.

**Fixes to apply before leaving this running unattended:**

1. **Daily ingestion schedule**, not every 30 minutes:
   ```python
   @app.timer_trigger(schedule="0 0 0 * * *", arg_name="mytimer", run_on_startup=False)
   ```
2. **Quiet the verbose Azure SDK logging** (every token request was logging full HTTP headers, which quietly ate into Application Insights' own separate free ingestion allowance):
   ```python
   logging.getLogger("azure").setLevel(logging.WARNING)
   ```
   Add this once, near the top of `function_app.py`.
3. **Set an Application Insights daily cap** as a hard backstop: the purple Application Insights resource → **Uso e custos estimados** → Daily cap → e.g. `0.05` GB/day. Once hit, it drops further telemetry instead of ever billing you.
4. **Actually create a budget alert** (and verify it saved): Cost Management + Billing → Orçamentos → + Criar → scope your subscription, amount €1–2/month, alert conditions at 80% and 100% of actual spend, your email. Confirm it appears back in the Orçamentos list afterward — the save can silently fail if you don't click all the way through.

If the database does exhaust its free allowance and auto-pauses (configured behavior, costs €0 for that itself), it resumes automatically on the 1st of the next month, or you can create a second free database (Azure allows up to 10 per subscription) to reset the clock immediately by re-running your `CREATE TABLE`/`CREATE VIEW` scripts against it.

## Step 14: Build the Power BI Report

1. Install Power BI Desktop (Microsoft Store, free).
2. **Power BI's cloud service requires a work/school-style email** — personal Gmail/Hotmail/Outlook.com addresses are blocked at sign-in. If you don't have one, create a free one inside your own Azure subscription's existing Entra ID tenant: Portal → Microsoft Entra ID → Utilizadores → + Novo utilizador → pick a username, Azure gives you `you@<random>.onmicrosoft.com` for free. Sign into Power BI with that.
3. It'll ask you to activate a **Fabric (Free)** license — accept it, genuinely free, may ask for phone verification only (no card).
4. **Obter dados → Web → Básico** → paste your live `/api/air-quality` URL → **Anónimo** → Conectar.
5. The result loads as a single "Record" column — click its expand icon (⇄), check all 6 fields, OK.
6. Fix `avg_value`'s type: right-click the column → **Alterar Tipo → Usando a Localidade...** → Número Decimal, locale **Inglês (Estados Unidos)** (the JSON uses a dot as the decimal separator; your Power BI locale may expect a comma, causing plain type conversion to error).
7. For any date field that auto-expands into a Year/Quarter/Month/Day hierarchy in a chart, click the field pill's dropdown and pick the plain date field instead of the hierarchy — otherwise line charts collapse into single points per year.
8. **Fechar e Aplicar.**

Build out visuals (slicer on `city`, bar/line charts on `avg_value` set to **Média** not **Soma**, filtered to a single `parameter` where relevant, a card for a headline number, a table for the raw rows). Style via the paint-roller **Formatar** pane on each visual (fonts, borders, titles) — select multiple visuals at once with Ctrl-click to format them together.

Save as `AirWatch.pbix`.

## Step 15: Publish to the Web

1. **Base** ribbon → **Publicar** → choose "O meu espaço de trabalho" → wait for upload → open the link.
2. In the browser (Power BI service), with the report open: **Ficheiro → Publicar na Web**.
3. If you hit *"Contacte o seu administrador para ativar a criação de código incorporado"* — this is a tenant setting that needs enabling, and since it's your own tenant, you can do it yourself:
   - Portal → Microsoft Entra ID → Funções e administradores → **Administrador Global** → + Adicionar atribuições → add your work account.
   - app.powerbi.com → gear icon → Portal de administração → Definições do inquilino → find **Publicar na Web** → Ativado → "Toda a organização" → Aplicar.
   - This can take several minutes to propagate. Retry "Publicar na Web" after waiting.
4. Confirm the public-sharing dialog, copy the generated link.

**Important limitation**: this published link does **not** auto-refresh. Power BI's scheduled refresh requires a Pro license (or Fabric capacity), not available on the free tier used here. To update it with new data, repeat: open `AirWatch.pbix` → Atualizar → Guardar → Publicar (the same report updates in place; it doesn't create a new link).

## Step 16: Push to GitHub

1. Clean up: delete any backup/scratch files you don't want public, move one-off debugging scripts into a `tools/` folder.
2. Check `.gitignore` includes at minimum: `local.settings.json`, `.venv/`, `__pycache__/`, the Azurite artifact files (`__azurite_db*__.json`, `__blobstorage__/`, `__queuestorage__/`, `AzuriteConfig`).
3. Create an empty public repo on GitHub (no auto-generated README — write your own).
4. ```
   git init
   git add .
   git status
   ```
   **Check the output carefully** — `local.settings.json` and `.venv` must not appear. If either does, stop and fix `.gitignore` before continuing.
5. ```
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```
6. Write a `README.md` covering: what the project does, the architecture, the live API and dashboard links, the stack, and — genuinely worth including — the real problems hit and fixed along the way (dead OpenAQ stations, the ODBC driver gap, the cost incident). That last part is good portfolio material; it shows real debugging rather than tutorial-following.
7. On the repo's GitHub page, click the gear icon next to **"About"** in the sidebar to add a description, the live link, and topic tags.

---

## Progress Checkpoint (for resuming in a new conversation)

**Done so far:**
- Free Azure account created, `airwatch-rg` resource group, `airwatch-db` (Sweden Central, serverless free tier, Entra-only auth)
- `stations` and `readings` tables created with a working foreign key constraint
- Local dev environment fully set up (Python 3.13 venv, Functions Core Tools, Azure CLI, logged in)
- OpenAQ API key obtained and stored safely in `local.settings.json`
- Ingestion function (`function_app.py`) written and working locally via Azurite, using Managed Identity (no passwords), with fixes for city/staleness/units bugs applied
- Diagnosed and fixed 8 dead/dormant station IDs, replaced with currently-active stations (see "Diagnosing and fixing dead stations" above); 10 of 12 cities now return real data, São Paulo and Cairo are a known/accepted OpenAQ coverage gap
- Built `daily_averages` SQL view (`GROUP BY` aggregation by city/parameter/day)
- Found and fixed a negative-value data-quality bug plus a related `measured_at` variable-naming bug in `fetch_and_insert`
- Confirmed a fully clean end-to-end run: no errors, no bad values, healthy data spread across cities

- Ingestion Function deployed to Azure (Flex Consumption, Linux, Python 3.13), Managed Identity enabled and granted `db_datareader`/`db_datawriter` on `airwatch-db`, app settings configured
- **Hit and fixed a real deployment blocker**: `pyodbc` failed in Azure with `Can't open lib 'ODBC Driver 17 for SQL Server' : file not found` — Azure's Linux Python Function runtime doesn't ship the system ODBC driver, and Flex Consumption doesn't support custom containers. Fix: switched to Microsoft's `mssql-python` package, which bundles its own driver binaries via pip, using `Authentication=ActiveDirectoryDefault` (works identically local and cloud, no code branching)
- Built and deployed the HTTP API Function (`get_air_quality`, route `/api/air-quality`, anonymous auth, optional `?city=` filter, queries `daily_averages`) — confirmed live and returning real JSON
- **Hit and fixed a real cost incident**: the 30-minute ingestion schedule never let the serverless SQL database auto-pause (needs ~1hr idle), exhausting the monthly free compute allowance (100,000 vCore-seconds) in about a week. The database auto-paused itself (as configured — €0 charged for that), but Application Insights' verbose SDK logging (every token request, every run) pushed slightly over its own free ingestion allowance, causing a small real charge (~€0.27). Fixes applied: silenced Azure SDK logging (`logging.getLogger("azure").setLevel(logging.WARNING)`), set an Application Insights daily cap (0.05 GB/day — hard-stops ingestion instead of billing), created a real monthly budget alert (80%/100%, this had silently failed to save the first time), and changed the ingestion schedule to once daily (`0 0 0 * * *`)
- Power BI Desktop set up: personal Microsoft accounts are blocked from Power BI/Fabric sign-in, so a free work-style user was created inside the existing Azure Entra ID tenant and used to sign in (free Fabric license, phone verification only, no card)
- Power BI report built locally against a static `sample-air-quality.json` (same schema as the live API) while the database was paused: city slicer, PM2.5-by-city bar chart, daily-average-by-pollutant line chart, headline card, and a full data table — styled (titles, axis labels, fonts, borders) and saved as `docs/AirWatch.pbix`
- Project cleaned and pushed to GitHub (public repo, working `.gitignore`, dev/debug scripts moved to `tools/`)

- SQL free-tier reset confirmed on schedule (Oct 1); ingestion re-verified working end to end (17 readings/10 cities) after the reset
- Power BI swapped from the local sample JSON to the live API (edited the "Origem" step's formula to `Json.Document(Web.Contents("..."))`, set the web source's privacy level to Público); report rebuilt and re-saved as `AirWatch.pbix`
- Published to web successfully (required granting the work account Global Administrator and enabling "Publicar na Web" in tenant settings — see Step 15); confirmed scheduled auto-refresh is NOT available on the free license, manual refresh + republish is the permanent way to update it
- `README.md` written and pushed to GitHub alongside this tutorial

**PROJECT COMPLETE.** Everything in this tutorial, steps 1 through 16, reflects the actual finished build: a daily-ingesting Azure Function, a public JSON API, and a published Power BI dashboard, all on free-tier Azure services.

**To resume** (e.g. for a rebuild, a new environment, or helping someone else follow this): start a new conversation, attach this tutorial file, and say which step you're picking up from.

---

## Final Step: Going Live Long-Term, or Shutting It All Down

Once the project is fully built and working, you have two paths. Pick whichever fits.

### Option A: Keep it running forever as a live demo

1. In the Azure Portal, search **"Subscriptions"** → select your Free Trial subscription.
2. Click **"Upgrade"** (Portuguese: "Atualizar").
3. Follow the prompts to convert to **Pay-As-You-Go**. This asks for a payment method, but as covered above, you are not charged unless you exceed the free monthly quotas — which this project's usage sits far below.
4. After upgrading, your resources keep running exactly as before, just without the 30-day ceiling. The budget alert from earlier keeps watching in the background regardless.
5. The ingestion Function and API keep running and updating automatically. The published Power BI dashboard does **not** — upgrading to PAYG doesn't unlock scheduled refresh (that needs Power BI Pro specifically, a separate cost). Keeping the dashboard current means manually repeating Atualizar → Guardar → Publicar in Power BI Desktop whenever you want it to show fresh data.

### Option B: You're done experimenting, and want to fully stop it (no upgrade needed)

If you'd rather not keep anything running long-term, the cleanest option is deleting the whole resource group — this removes every resource we created (SQL server, database, Function Apps) in one action, so nothing lingers or risks billing later:

1. Go to your resource group **`airwatch-rg`**.
2. Click **"Delete resource group"** (Portuguese: "Eliminar grupo de recursos") near the top.
3. Type the resource group name to confirm.
4. Click **Delete**. Within a few minutes, everything inside it is gone.

If you just want to **pause** things temporarily instead of deleting permanently (e.g., taking a break but might come back):
- The **SQL database** already auto-pauses itself when idle — no action needed.
- To stop the **Function Apps** from running on their schedule, go to each Function App → **Overview** → click **Stop**. Click **Start** again whenever you want to resume.

Either way, check **Cost Management + Billing → Cost analysis** afterward to confirm everything shows €0 going forward.
