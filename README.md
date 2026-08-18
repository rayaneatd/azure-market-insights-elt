# Azure Market Insights — IGDB ELT Pipeline

A production-grade ELT pipeline that ingests video game market data from the [IGDB API](https://api-docs.igdb.com/) into Azure Data Lake Storage Gen2 and PostgreSQL, with a real-time governance dashboard and an event-driven fallback architecture.

Built as a Python-focused portfolio project. The goal was not just to move data, but to build something resilient enough to handle the kind of problems that actually show up in production — rate limits, schema drift, partial failures, event-driven replays, and full data lineage with zero data loss.

---

## Architecture Overview

```
                          ┌──────────────────────────────────┐
                          │        IGDB REST API (v4)        │
                          │  /games /genres /platforms etc.   │
                          └──────────────┬───────────────────┘
                                         │  HTTPX + Token Bucket (4 req/s)
                                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        INGESTION ENGINE (Python)                       │
│                                                                        │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────────┐  │
│  │  Fallback Event  │──▶│ _construct_tables │──▶│  Batch Fetch Loop │  │
│  │  Queue (FIFO)    │    │      _dict()      │    │  + ADLS Persist   │  │
│  └─────────────────┘    └──────────────────┘    └───────────────────┘  │
│           ▲                                              │             │
│           │ PENDING events consumed first                │             │
│           │ before incremental checkpoints               ▼             │
│  ┌────────┴──────────────────────────────────────────────────────────┐ │
│  │                   PostgreSQL — logs schema                        │ │
│  │  ingestion_runs │ ingestion_checkpoints │ batch_logs              │ │
│  │  schema_history │ fallback_events                                 │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
         │                                              │
         ▼                                              ▼
┌─────────────────────┐                    ┌─────────────────────────┐
│  Azure Data Lake    │                    │  Governance Dashboard   │
│  Gen2 / Azurite     │                    │  (Flask + Frutiger Aero)│
│                     │                    │                         │
│  Bronze/Raw Layer   │                    │  KPIs, Runs, Batches,   │
│  {endpoint}/        │                    │  Checkpoints, Schema    │
│    {cursor}_{off}   │                    │  Drift, Fallback Queue  │
│      .json          │                    │                         │
└─────────────────────┘                    └─────────────────────────┘
```

---

## What it does

`main.py` acts as the orchestrator. Each run is fully linear and idempotent:

1. **Checks for pending fallback events** in `logs.fallback_events`. If a replay has been scheduled (via the dashboard or directly in the database), the pipeline processes it first — fetching only the time window specified by `start_watermark` → `end_watermark`.

2. **Falls back to incremental ingestion** if no events are pending. Reads the last checkpoint per table from `logs.ingestion_checkpoints` and queries `where updated_at >= last_watermark`.

3. **Fetches raw data** from 5 IGDB endpoints (`/games`, `/genres`, `/platforms`, `/franchises`, `/companies`) with automatic throttling via a token bucket (4 req/s) and progressive cursor-based pagination with offset wrapping at 10,000.

4. **Persists every raw page** as immutable JSON in Azure Data Lake (`{endpoint}/{cursor}_{offset}.json`), creating a full audit trail in the Bronze/Raw zone.

5. **Logs everything** — every batch attempt is recorded in `logs.batch_logs` with the Apicalypse query sent, response time, record count, and any errors. Every ingestion run is tracked in `logs.ingestion_runs` with start/end times and final status.

6. **Fires Discord alerts** on failures with enough context to debug without looking at logs.

---

## Event-Driven Fallback Architecture

The pipeline decouples replay/backfill from the main incremental checkpoint. Instead of mutating the checkpoint to trigger a re-ingestion (which risks corrupting the incremental state), fallbacks are modeled as **events** in a FIFO queue:

```sql
logs.fallback_events
├── event_id       UUID (auto-generated)
├── table_name     VARCHAR — which table to replay
├── start_watermark BIGINT — Unix timestamp start of the window
├── end_watermark   BIGINT — Unix timestamp end of the window
├── status          PENDING → IN_PROGRESS → COMPLETED / FAILED
├── records_processed INT — running total
└── error_message   TEXT — if something went wrong
```

**How it works:**
1. An admin creates a fallback event (via the dashboard or SQL) specifying `table_name`, `start_watermark`, and `end_watermark`.
2. On the next pipeline run, `_construct_tables_dict()` checks for `PENDING` events before reading checkpoints.
3. If events exist, the pipeline marks them `IN_PROGRESS`, fetches the specified time window, and marks them `COMPLETED` or `FAILED`.
4. The incremental checkpoint is **never touched** during a fallback — the two systems are fully decoupled.

This means you can replay any arbitrary time window for any table without disrupting the live incremental pipeline.

---

## Adaptive Schema Management

IGDB doesn't publish a changelog. Fields get added, renamed, or quietly removed without notice. The schema is declared in Python (`tables_schema.py`) using **Patito** (Pydantic + Polars), one class per table. That file is the single source of truth.

**Soft change — a new column appears in the API:**
- The pipeline continues without interruption (`model_config = {"extra": "ignore"}`)
- The new column is logged in `logs.schema_history` with status `NEW_COLUMN`
- A Discord notification fires so a human can decide whether to include it
- Once added to `tables_schema.py`, the next run picks it up automatically

**Breaking change — a required field is missing or a type has changed:**
- Affected records are flagged and the error is logged
- The pipeline continues processing what it can
- A Discord alert fires with full error context

The raw data in ADLS is always complete and untouched. Nothing is ever permanently lost.

---

## Governance Dashboard

A real-time operational dashboard built with Flask and a **Frutiger Aero** design aesthetic (glassmorphism, gradients, micro-animations). Accessible locally or via public tunnel for cross-region access.

**Features:**
- 📊 **KPI cards** — Total runs, success/failure ratio, active overrides, total records ingested
- 🚀 **Ingestion Runs** — Full history with status badges, timing, and error messages
- 📋 **Fallback Event Queue** — FIFO event list with real-time status tracking, plus a modal to create new events
- 📍 **Incremental Checkpoints** — Current watermark state per table with quick-replay buttons
- 📜 **Batch Logs** — Every API call logged with cursor, offset, record count, duration, and the raw Apicalypse query
- 🔍 **Schema Drift Audit** — Detected column changes with timestamps and run IDs
- 🔎 **Filters & Sorting** — Full-text search and sortable columns on every table

**Security:**
- 🔒 Full-screen login lock — nothing is accessible without authentication
- 👤 **RBAC** — `ADMIN` gets full access (including fallback creation), `VIEWER` gets read-only
- 🛡️ `@login_required` on all API routes, RBAC guards on destructive actions
- 📝 HTTP access logs directed to `app/server.log` (no terminal spam)

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.13 |
| HTTP Client | `httpx` (async-ready, HTTP/2) |
| Schema Validation | `patito` (Pydantic v2 + Polars) |
| Serialization | `msgspec` (zero-copy, high-perf) |
| DataFrame Engine | `polars` (Rust-backed, no Pandas) |
| Database | PostgreSQL via `psycopg 3` + `psycopg-pool` |
| Raw Storage | Azure Data Lake Storage Gen2 / Azurite |
| Auth (Cloud) | `azure-identity` (DefaultAzureCredential) |
| Auth (Local) | Connection string via `.env` |
| Dashboard | Flask + Vanilla HTML/CSS/JS |
| Alerting | Discord Webhooks |
| Package Manager | `uv` |
| Local Infra | Docker Compose (PostgreSQL + Azurite) |

---

## Running it locally

### Prerequisites
- Docker (for PostgreSQL and Azurite)
- Python 3.13+ with [`uv`](https://docs.astral.sh/uv/)
- A free [Twitch developer account](https://api-docs.igdb.com/#getting-started) for IGDB API credentials

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/rayaneatd/azure-market-insights-elt.git
cd azure-market-insights-elt

# 2. Install dependencies
uv sync

# 3. Spin up local infrastructure
docker compose up -d

# 4. Add your credentials to .env
#    See example.env for required variables

# 5. Run the pipeline
uv run python main.py

# 6. (Optional) Start the governance dashboard
uv run python app/server.py
# → http://127.0.0.1:5000

# 7. (Optional) Expose dashboard publicly (e.g. for remote access)
npx localtunnel --port 5000
```

---

## Project Structure

```
.
├── main.py                          # Entry point — orchestrates the full pipeline
├── pyproject.toml                   # Dependencies and project config (uv)
│
├── src/
│   ├── handle_ingestion.py          # Core ingestion engine (event-driven + incremental)
│   ├── tables_schema.py             # Patito/Pydantic models — schema SSOT
│   ├── database_auth.py             # PostgreSQL connection pool (psycopg 3)
│   ├── datalake_service_client.py   # Azure ADLS / Azurite client init
│   ├── igdb/
│   │   ├── auth.py                  # IGDB OAuth2 token management
│   │   ├── client.py                # IGDB API client (httpx + msgspec)
│   │   └── rate_limit.py            # Token bucket rate limiter (4 req/s)
│   ├── secrets/
│   │   ├── project_credentials.py   # Credential loading
│   │   └── project_environment.py   # Environment detection (dev/prod)
│   └── utils/
│       ├── database_interaction.py   # All PostgreSQL helpers (checkpoints, logs, fallback events)
│       ├── datalake_interaction.py   # ADLS read/write helpers
│       └── log_messages.py           # Discord alerting + structured logging
│
├── app/
│   ├── server.py                    # Flask dashboard backend (RBAC, APIs)
│   ├── style.css                    # Frutiger Aero design system
│   ├── templates/
│   │   └── index.html               # Dashboard SPA (login, KPIs, tables, modals)
│   ├── backend/
│   │   └── functions.py             # Dashboard data access layer
│   └── sql/
│       └── log_schemas.sql          # DDL for all governance tables
│
├── docs/
│   └── schema/                      # Data model diagrams (Draw.io)
├── docker-compose.yml
└── example.env
```

---

## Design Decisions

**Why event-driven fallback instead of checkpoint mutation?**
Mutating the checkpoint to trigger a replay is fragile — if the replay fails halfway, the incremental state is corrupted and you lose your place. By modeling fallbacks as events in a separate queue, the two systems are fully decoupled. The checkpoint always reflects the true incremental frontier, and replays can be retried independently.

**Why Patito instead of plain Pydantic?**
Patito extends Pydantic models to also validate Polars DataFrames. This means the same schema class validates individual records at ingestion time _and_ entire DataFrames at transformation time. One source of truth, two validation layers.

**Why Polars instead of Pandas?**
Polars is Rust-backed, uses Apache Arrow memory format, and is significantly faster for the column-oriented transforms this pipeline needs. It also has a stricter type system that catches bugs earlier.

**Why store raw JSON before transforming?**
This is the Bronze/Raw layer pattern. If a transformation bug corrupts clean data in PostgreSQL, you can always re-run the transformation against the untouched raw files. You never have to call the API again to recover. The raw data is the immutable source of truth.

**Why UPSERT instead of INSERT?**
Because pipelines get restarted. The watermark overlap means some records will be fetched twice. `ON CONFLICT DO UPDATE` makes the operation idempotent. Run it once or a hundred times, the result in PostgreSQL is always the same.

---

## Roadmap

- [ ] **Analytics Layer** — Polars-based transformation from Raw to Analytics schema
- [ ] **Makefile** — One-command orchestration for all services
- [ ] **Discovery Job** — Automated detection of new IGDB columns (cron-based)
- [ ] **Airflow/Prefect** — Proper scheduling and observability (currently manual trigger)
- [ ] **Azure Deployment** — ACA or VM with Managed Identity replacing local connection strings
