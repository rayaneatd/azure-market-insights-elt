# Azure Market Insights — ELT Pipeline

A production-style ELT pipeline that ingests video game market data from the [IGDB API](https://api-docs.igdb.com/) into Azure Data Lake Storage Gen2, validates and transforms it using Python, then loads it into a PostgreSQL database for analysis.

Built as a Python-focused portfolio project. The goal was not just to move data, but to build something resilient enough to handle the kind of problems that actually show up in production — rate limits, schema drift, partial failures, and the need for full data lineage.

---

## What it does

The pipeline runs every 5 minutes. `main.py` acts as the orchestrator and handles the full flow end to end:

1. **Fetches raw data** from 5 IGDB endpoints (`/games`, `/genres`, `/platforms`, `/release_dates`, `/companies`) with built-in retry logic (up to 5 attempts) and automatic throttling to stay within the 4 req/s API limit.
2. **Stores the raw JSON** as-is in Azure Data Lake (or a local Azurite emulator), creating an immutable audit trail of every API response.
3. **Validates and transforms** each batch using Pydantic schemas defined in `tables_schema.py`. This is where the pipeline decides what's clean data, what's a schema drift event, and what needs to go to quarantine.
4. **Loads clean data** into PostgreSQL using idempotent `UPSERT` operations, so re-runs never create duplicates.

If anything goes wrong at any step, a Discord notification fires with enough context to debug it without looking at logs.

---

## The part I'm most proud of: adaptive schema management

IGDB doesn't publish a changelog. Fields get added, renamed, or quietly removed without notice. Most pipelines either crash on this or silently drop data. This one doesn't.

The schema is declared in Python (`tables_schema.py`), one Pydantic class per table. That file is the single source of truth. When the pipeline runs and encounters a field it doesn't recognize, here's what happens depending on the type of change:

**Soft change — a new column appears in the API response:**
- The pipeline continues without interruption
- The new column name and detection timestamp are logged in `new_columns.json` on ADLS
- A Discord notification is sent so a human can decide whether to include it
- Once added to `tables_schema.py`, the next scheduled run picks it up automatically
- A backfill script re-processes all raw files stored between the detection date and the inclusion date to retroactively populate the new column in PostgreSQL

**Breaking change — a required field is missing or a type has changed:**
- Affected rows are routed to a quarantine table in PostgreSQL instead of being silently dropped
- The pipeline continues processing the rows it can
- A Discord alert is sent with the error details
- Once the schema is corrected, a reconciliation script replays the quarantined rows

This means the raw data in ADLS is always complete, and nothing is ever permanently lost.

---

## Incremental loading (Watermarking)

The pipeline doesn't re-fetch the entire IGDB database on every run. A watermark file stored in the `control/` container on ADLS tracks the timestamp of the last successful ingestion per endpoint. Each run queries the API using `updated_at > last_watermark - 1h`, with a one-hour overlap to account for indexing delays on IGDB's side. Since the load step uses `UPSERT`, overlapping records are harmlessly overwritten.

---

## Tech stack

| Layer | Tool |
|---|---|
| Orchestration | Python (`main.py`, `tenacity` for retries) |
| Raw storage | Azure Data Lake Storage Gen2 / Azurite (local) |
| Schema validation | Pydantic v2 |
| Transformation | Pandas |
| Database | PostgreSQL (`psycopg2`, SQLAlchemy) |
| Auth (cloud) | Azure `DefaultAzureCredential` (Managed Identity) |
| Auth (local) | Connection string via `.env` |
| Alerting | Discord Webhooks |
| Local environment | Docker Compose |

---

## Running it locally

The only hard requirement is Docker. Everything else — PostgreSQL, the Azurite storage emulator, and the environment config — is handled by Docker Compose.

```bash
# 1. Clone the repo
git clone https://github.com/rayaneatd/azure-market-insights-elt.git
cd azure-market-insights-elt

# 2. Spin up the local infrastructure
docker compose up -d

# 3. Add your IGDB credentials to the generated .env file
#    (You'll need a free Twitch developer account to get a client_id and client_secret)
#    See: https://api-docs.igdb.com/#getting-started

# 4. Run the pipeline
python main.py
```

If you don't want to use Docker, you can run PostgreSQL and Azurite manually and configure the `.env` file yourself. See `example.env` for the required variables.

---

## Project structure

```
.
├── main.py                  # Entry point and orchestrator
├── src/
│   ├── handle_auth.py       # Azure credential setup (dev vs. prod)
│   ├── tables_schema.py     # Pydantic models — the schema SSOT
│   ├── secrets/             # Environment variable loading
│   └── utils/
│       └── log_messages.py  # Discord alerting and logging helpers
├── docs/
│   └── schema/              # Data model diagrams (Draw.io)
├── docker-compose.yml
├── pyproject.toml
└── example.env
```

---

## Design decisions worth noting

**Why Python classes instead of YAML for the schema?**
YAML schema definitions are common but disconnected from the code that uses them. Defining the schema as Pydantic classes means the validation logic, the type coercion, and the schema documentation all live in the same place. When you update the schema, you update one file, and everything downstream adjusts.

**Why store raw JSON before transforming?**
This is the core principle of the Bronze/Raw layer pattern. If a transformation bug corrupts clean data in PostgreSQL, you can always re-run the transformation step against the untouched raw files. You never have to call the API again to recover.

**Why UPSERT instead of INSERT?**
Because pipelines get restarted. The watermark overlap means some records will be fetched twice. `ON CONFLICT DO UPDATE` makes the operation idempotent — it doesn't matter how many times you run it, the result in PostgreSQL is always the same.

---

## What's next

- Airflow or Prefect for proper scheduling and observability (currently a simple cron / manual trigger)
- A lightweight dashboard to visualize the pipeline run history and quarantine stats
- Deployment to Azure (ACA or a small VM) with Managed Identity replacing the local connection string
