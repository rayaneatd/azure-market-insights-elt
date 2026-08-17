# pyrefly: ignore [missing-import]
import json
import traceback
import uuid
import time
from sqlalchemy.engine import Engine
from src.igdb.client import extract_igdb_data
from src.igdb.rate_limit import TokenBucket
from src.tables_schema import *
from src.utils.log_messages import AlertLevel, log_to_discord
from azure.storage.filedatalake import DataLakeServiceClient
from azure.storage.blob import BlobServiceClient
from src.utils.datalake_interaction import (
    write_into_raw,
    Containers
)
from src.utils.database_interaction import (
    start_ingestion_run,
    complete_ingestion_run,
    get_checkpoints,
    upsert_checkpoint,
    upsert_fallback_checkpoint,
    log_batch
)

# IGDB API rate limit: 4 requests per second.
# TokenBucket ensures we do not exceed this limit.
bucket = TokenBucket(capacity=4, fill_rate=4)


def _construct_tables_dict(db_engine: Engine) -> dict[type, dict]:
    """
    Retrieves checkpoints from Postgres and resolves starting metadata for each table class.
    Returns:
        dict[type, dict]: Map of Model -> {
            "cursor": int,
            "last_id": int,
            "offset": int,
            "is_override": bool
        }
    """
    defined_classes = BaseIGDBSchema.__subclasses__()
    checkpoints = get_checkpoints(db_engine)

    resolved = {}
    for cls in defined_classes:
        name = cls.__name__
        if name not in checkpoints:
            # Create a default checkpoint in PostgreSQL
            upsert_checkpoint(
                engine=db_engine,
                table_name=name,
                current_watermark=cls._starting_point,
                last_id=0,
                offset_val=0,
                run_id=None,
                is_override_active=False
            )
            # Fetch newly created entry to match structure
            checkpoints = get_checkpoints(db_engine)

        ckpt = checkpoints[name]
        if ckpt["is_override_active"]:
            resolved[cls] = {
                "cursor": ckpt["fallback_watermark"],
                "last_id": 0,
                "offset": 0,
                "is_override": True
            }
        else:
            resolved[cls] = {
                "cursor": ckpt["current_watermark"],
                "last_id": ckpt["last_id"],
                "offset": ckpt["offset_val"],
                "is_override": False
            }

    return resolved


def _save_raw_batch(azure_client: DataLakeServiceClient | BlobServiceClient, Model: type, batch: list[dict], cursor: int, offset: int) -> None:
    """
    Persists a raw page of records to the bronze/raw zone in ADLS.
    Path pattern keeps pages uniquely addressable and roughly time-ordered.
    """
    path = f"{Model._endpoint}/{cursor}_{offset}.json"
    write_into_raw(
        azure_client,
        Containers.Data.value,
        path,
        json.dumps(batch).encode()
    )


def ingest_batches_to_postgres(azure_client: DataLakeServiceClient | BlobServiceClient) -> None:
    """
    PLACEHOLDER — future implementation.
    Reads newly landed raw/bronze batches from ADLS and loads them into Postgres.
    """
    pass


def do_ingestion(azure_client: DataLakeServiceClient | BlobServiceClient, db_engine: Engine) -> None:
    """
    Main ingestion pipeline. Iterates through all defined schemas, fetches data
    from the IGDB API using pagination, persists raw batches to ADLS, and updates
    the watermark state in Postgres after each page.
    """
    run_id = str(uuid.uuid4())
    start_ingestion_run(db_engine, run_id)

    run_status = "COMPLETED"
    run_error = None

    try:
        tables = _construct_tables_dict(db_engine)

        for Model, meta in tables.items():
            cursor = meta["cursor"]
            last_id = meta["last_id"]
            offset = meta["offset"]
            max_seen = cursor

            # Consume override flag immediately in the DB if active
            if meta["is_override"]:
                upsert_checkpoint(
                    engine=db_engine,
                    table_name=Model.__name__,
                    current_watermark=cursor,
                    last_id=last_id,
                    offset_val=offset,
                    run_id=run_id,
                    is_override_active=False
                )

            try:
                while True:
                    bucket.acquire()

                    query = Model.build_query(
                        last_update_value=cursor,
                        last_id=last_id,
                        offset=offset
                    )

                    print(f"QUERY [{Model.__name__}]: {query!r}", flush=True)
                    log_to_discord(f"QUERY [{Model.__name__}]: {query!r}", level=AlertLevel.INFO)

                    start_time = time.perf_counter()
                    batch = []
                    batch_status = "SUCCESS"
                    batch_err = None

                    try:
                        batch = extract_igdb_data(
                            url=f"{BASE_IGDB_URL}{Model._endpoint}",
                            query=query,
                            timeout=10
                        )
                    except Exception as extract_err:
                        batch_status = "FAILED"
                        batch_err = str(extract_err)
                        raise
                    finally:
                        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                        log_batch(
                            engine=db_engine,
                            run_id=run_id,
                            table_name=Model.__name__,
                            layer="RAW",
                            status=batch_status,
                            cursor_value=cursor,
                            offset_value=offset,
                            records_count=len(batch) if batch else 0,
                            duration_ms=elapsed_ms,
                            query_sent=query,
                            error_message=batch_err
                        )

                    if not batch:
                        # Clean finish of records; update fallback state to safety point
                        upsert_fallback_checkpoint(db_engine, Model.__name__, max_seen)
                        break

                    # Validate records
                    for record in batch:
                        if "updated_at" not in record or "id" not in record:
                            raise ValueError(
                                f"Record missing 'updated_at' or 'id' for {Model.__name__}: {record}"
                            )

                    # Persist raw page to ADLS Raw zone
                    _save_raw_batch(azure_client, Model, batch, cursor, offset)

                    batch_max_ts = max(r["updated_at"] for r in batch)
                    batch_max_id_for_ts = max(r["id"] for r in batch if r["updated_at"] == batch_max_ts)

                    if batch_max_ts > max_seen:
                        max_seen = batch_max_ts
                        last_id = batch_max_id_for_ts
                    else:
                        last_id = max(last_id, batch_max_id_for_ts)

                    # Update progressive checkpoint after every successful page
                    upsert_checkpoint(
                        engine=db_engine,
                        table_name=Model.__name__,
                        current_watermark=max_seen,
                        last_id=last_id,
                        offset_val=offset,
                        run_id=run_id
                    )

                    if len(batch) < 500:
                        # Success complete
                        upsert_fallback_checkpoint(db_engine, Model.__name__, max_seen)
                        break

                    offset += 500
                    if offset >= 10000:
                        cursor = max_seen
                        offset = 0

            except Exception as e:
                run_status = "FAILED"
                tb = traceback.format_exc()
                msg = f"Unexpected failure ingesting {Model.__name__}: {e}\n{tb}"
                max_len = 1900
                if len(msg) > max_len:
                    msg = msg[:200] + "\n...\n" + msg[-(max_len - 200):]
                log_to_discord(msg=f"```\n{msg}\n```", level=AlertLevel.WARNING)
                continue

    except Exception as e:
        run_status = "FAILED"
        run_error = str(e)
        log_to_discord(f"Pipeline orchestration run failed: {e}", level=AlertLevel.ERROR)
    finally:
        complete_ingestion_run(db_engine, run_id, run_status, run_error)