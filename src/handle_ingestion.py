# pyrefly: ignore [missing-import]
import json
import traceback

from src.igdb.client import extract_igdb_data
from src.igdb.rate_limit import TokenBucket
from src.tables_schema import *
from src.utils.log_messages import AlertLevel, log_to_discord
from azure.storage.filedatalake import DataLakeServiceClient
from azure.storage.blob import BlobServiceClient
from src.utils.datalake_interaction import (
    read_from_raw,
    write_into_raw,
    Containers
)

# Example structure of the watermark JSON stored in ADLS:
# {
#     "games": 1754361600,
#     "release_dates": 1754361600,
#     "genres": 1754361600,
#     "platforms": 1754361600,
#     "companies": 1754361600
# }

# IGDB API rate limit: 4 requests per second.
# TokenBucket ensures we do not exceed this limit.
bucket = TokenBucket(capacity=4, fill_rate=4)
BASE_IGDB_URL = "https://api.igdb.com/v4/"  # Adjust if defined elsewhere


def _construct_tables_dict(azure_client: DataLakeServiceClient | BlobServiceClient) -> dict[type, int]:
    """
    Retrieves the current watermark state from ADLS and maps it to the schema classes.
    """
    defined_classes: list[type] = BaseIGDBSchema.__subclasses__()

    raw = read_from_raw(azure_client, Containers.Control.value, "watermark.json")
    watermark_str: dict = json.loads(raw) if raw else {}

    missing = [cls for cls in defined_classes if cls.__name__ not in watermark_str]

    if missing:
        for cls in missing:
            watermark_str[cls.__name__] = cls._starting_point
        write_into_raw(
            azure_client,
            Containers.Control.value,
            "watermark.json",
            json.dumps(watermark_str).encode()
        )

    return {cls: watermark_str[cls.__name__] for cls in defined_classes}


def _persist_watermark(azure_client, tables: dict[type, int]) -> None:
    """Small helper to avoid duplicating the serialization logic at every checkpoint."""
    final = {cls.__name__: ts for cls, ts in tables.items()}
    write_into_raw(
        azure_client,
        Containers.Control.value,
        "watermark.json",
        json.dumps(final).encode()
    )


def _save_raw_batch(azure_client, Model, batch: list[dict], cursor: int, offset: int) -> None:
    """
    Persists a raw page of records to the bronze/raw zone in ADLS.
    Path pattern keeps pages uniquely addressable and roughly time-ordered.
    """
    path = f"{Model._endpoint}/{cursor}_{offset}.json"
    write_into_raw(
        azure_client,
        Containers.Data.value,  # adapte le nom du container si besoin
        path,
        json.dumps(batch).encode()
    )


def ingest_batches_to_postgres(azure_client: DataLakeServiceClient | BlobServiceClient) -> None:
    """
    PLACEHOLDER — future implementation.

    This function will be triggered on a cumulative 8-minute schedule (separate from
    do_ingestion) to read newly landed raw/bronze batches from ADLS and load them into
    Postgres (upsert by id, dedup, schema mapping, etc.).

    Not wired up yet: intentionally left as a no-op so the trigger/scheduler can be
    plugged in without touching do_ingestion's contract.
    """
    # TODO: implement batch ingestion into Postgres
    pass


def do_ingestion(azure_client: DataLakeServiceClient | BlobServiceClient) -> None:
    """
    Main ingestion pipeline. Iterates through all defined schemas, fetches data
    from the IGDB API using pagination, persists raw batches to ADLS, and updates
    the watermark state after each page (not just at the end of a table) so that
    a failure mid-table doesn't lose progress.

    Pagination logic:
    - Uses offset-based pagination (limit 500 per request).
    - If offset reaches 10,000 (IGDB limit), shifts the query cursor to the max
      `updated_at` timestamp seen so far and resets the offset to 0.

    Note: retry/backoff on transient API errors is handled inside extract_igdb_data.
    The try/except here is a safety net for non-transient failures (bad data,
    logic errors, unexpected exceptions) so one table's failure doesn't kill the run.
    """
    tables = _construct_tables_dict(azure_client)

    for Model, watermark in tables.items():
        cursor = watermark
        last_id = 0
        offset = 0
        max_seen = watermark

        try:
            while True:
                bucket.acquire()

                query = Model.build_query(last_update_value=cursor, last_id=last_id, offset=offset)
                batch = extract_igdb_data(url=f"{BASE_IGDB_URL}{Model._endpoint}", query=query, timeout=10)
                if not batch:
                    break

                # Validate records before using them — fail loud and clear rather than
                # a bare KeyError buried in a max() generator expression.
                for record in batch:
                    if "updated_at" not in record or "id" not in record:
                        raise ValueError(
                            f"Record missing 'updated_at' or 'id' for {Model.__name__}: {record}"
                        )

                # Persist the raw page to the bronze zone before advancing the cursor,
                # so a crash between fetch and checkpoint never leaves a "seen but not saved" page.
                _save_raw_batch(azure_client, Model, batch, cursor, offset)

                batch_max_ts = max(r["updated_at"] for r in batch)
                batch_max_id_for_ts = max(r["id"] for r in batch if r["updated_at"] == batch_max_ts)

                if batch_max_ts > max_seen:
                    max_seen = batch_max_ts
                    last_id = batch_max_id_for_ts
                else:
                    last_id = max(last_id, batch_max_id_for_ts)

                # Checkpoint after every successful page: update in-memory state and
                # flush it to ADLS immediately, instead of waiting for the whole table.
                tables[Model] = max_seen
                _persist_watermark(azure_client, tables)

                if len(batch) < 500:
                    break

                offset += 500

                if offset >= 10000:
                    cursor = max_seen
                    offset = 0

        except Exception as e:
            log_to_discord(
                msg=f"Failed to ingest {Model.__name__}: {e}\n{traceback.format_exc()}",
                level=AlertLevel.ERROR
            )
            continue