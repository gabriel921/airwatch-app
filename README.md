# AirWatch

A real-time air quality monitoring pipeline. Serverless, passwordless, and free to run.

AirWatch pulls live air quality readings for 12 cities worldwide from the [OpenAQ](https://openaq.org) API, stores them in Azure SQL, aggregates them into daily averages, and exposes that data through a public JSON API — all visualized in a Power BI dashboard.

**Live API:** `https://airwatch-func-gabriel-e8bjg6f0f5a7cbf4.swedencentral-01.azurewebsites.net/api/air-quality`
*(optionally filter with `?city=London`)*

**Live dashboard:** https://app.powerbi.com/view?r=eyJrIjoiYTIyZGZlMDctYmQ2Ny00M2JkLWI2OTAtMGY5MGJjN2Y1YTY1IiwidCI6IjYzMjIxMWEwLWUxY2MtNGI3YS1iNWU4LTUyZjY1ODA0NDZiNSJ9

## What it does

- Every day, an Azure Function pulls the latest PM2.5, PM10, NO2, O3 and other readings for 12 cities (Lisbon, London, Paris, New York, Los Angeles, São Paulo, Cairo, Delhi, Beijing, Tokyo, Sydney, Nairobi) from OpenAQ's public station network.
- Readings are filtered to consistent units (µg/m³ only) and freshness (rejects stale or invalid data), then stored in Azure SQL.
- A SQL view aggregates raw readings into daily city/pollutant averages.
- A second Azure Function exposes that view as a public, anonymous JSON API.
- A Power BI report turns it into an interactive dashboard: filter by city, compare pollutants, track trends over time.

## Architecture

```
OpenAQ API
    │
    ▼
Azure Function (timer trigger, daily)  ──►  Azure SQL Database
                                                   │
                                                   ▼
                                          daily_averages (view)
                                                   │
                                                   ▼
                              Azure Function (HTTP trigger) ──► JSON API
                                                   │
                                                   ▼
                                            Power BI report
```

## Stack

- **Compute:** Azure Functions, Python 3.13, Flex Consumption (Linux)
- **Database:** Azure SQL Database, serverless, free tier
- **Auth:** Microsoft Entra ID Managed Identity — no passwords or connection strings anywhere in the code
- **DB driver:** [`mssql-python`](https://pypi.org/project/mssql-python/) (Microsoft's official pip-installable driver — used instead of `pyodbc` because Azure's Linux Python runtime doesn't ship the system ODBC driver)
- **Visualization:** Power BI
- **Cost:** built entirely on always-free tiers; see [`docs/AirWatch_Tutorial.md`](docs/AirWatch_Tutorial.md) for exactly how the free-tier math works out, and a real incident where a too-frequent schedule briefly exceeded it

## Repository structure

```
function_app.py          # Both Azure Functions: ingestion (timer) and API (HTTP)
host.json                 # Azure Functions host configuration
requirements.txt          # Python dependencies
docs/
  AirWatch.pbix            # Power BI report
  sample-air-quality.json  # Sample API response (matches live schema)
  AirWatch_Tutorial.md      # Full build log / step-by-step tutorial
tools/
  find_active_stations.py  # Finds currently-reporting OpenAQ stations near a city
  diagnostic_check.py       # Inspects a station's raw sensor data
```

## Running it yourself

The full build — including every problem hit along the way and how it was solved — is documented step by step in [`docs/AirWatch_Tutorial.md`](docs/AirWatch_Tutorial.md). Short version:

1. Create an Azure SQL Database (serverless, free tier) and run the schema in `docs/schema.sql` *(if included)*.
2. Create an Azure Function App (Flex Consumption, Linux, Python 3.13) in the same resource group.
3. Enable the Function App's system-assigned Managed Identity and grant it `db_datareader`/`db_datawriter` on the database.
4. Set the app settings `OPENAQ_API_KEY`, `SQL_SERVER`, `SQL_DATABASE`.
5. Deploy `function_app.py`.

## Notable problems solved along the way

- **Dead stations:** 8 of the original 12 OpenAQ station IDs turned out to be dormant records that stopped reporting years ago. Fixed by querying OpenAQ's `/v3/locations` endpoint sorted by last-report time to find genuinely active stations.
- **Missing ODBC driver:** Azure's Linux Python Functions runtime doesn't include the SQL Server ODBC driver, breaking `pyodbc`. Fixed by switching to `mssql-python`, which bundles its own driver.
- **Free-tier exhaustion:** An overly frequent ingestion schedule (every 30 minutes) never let the serverless database idle long enough to auto-pause, burning through a month's free compute allowance in about a week. Fixed by moving to a daily schedule and adding hard usage caps.

## License

MIT
