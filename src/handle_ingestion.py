# pyrefly: ignore [missing-import]
from src.igdb.client import extract_igdb_data
from src.igdb.rate_limit import TokenBucket
from src.tables_schema import *
from src.utils.log_messages import AlertLevel,log_to_discord
from azure.storage.filedatalake import DataLakeServiceClient
from azure.storage.blob import BlobServiceClient
from src.utils.datalake_interaction import (
    read_from_raw,
    write_into_raw,
    Containers
)
import json

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

    This function:
    1. Reads the watermark JSON file from ADLS.
    2. Detects any new schema classes defined in `tables_schema.py` that are missing from the watermark.
    3. Initializes missing schemas with their default `_starting_point` timestamp.
    4. Writes the updated watermark back to ADLS if new schemas were added.

    Args:
        azure_client: Client to interact with Azure Data Lake / Blob Storage.

    Returns:
        A dictionary mapping schema classes to their last updated timestamp (watermark).
    """
    defined_classes: list[type] = BaseIGDBSchema.__subclasses__()

    # Fetch the existing watermark state from ADLS
    raw = read_from_raw(azure_client, Containers.Control.value, "watermark.json")
    watermark_str: dict = json.loads(raw) if raw else {}

    # Identify schema classes that are not yet tracked in the watermark file
    missing = [cls for cls in defined_classes if cls.__name__ not in watermark_str]

    # Initialize missing schemas with their default starting points and persist changes
    if missing:
        for cls in missing:
            watermark_str[cls.__name__] = cls._starting_point
        write_into_raw(
            azure_client, 
            Containers.Control.value, 
            "watermark.json", 
            json.dumps(watermark_str).encode()
        )

    # Map the schema classes directly to their watermark timestamps for easier iteration
    return {cls: watermark_str[cls.__name__] for cls in defined_classes}


def do_ingestion(azure_client: DataLakeServiceClient | BlobServiceClient) -> None:
    """
    Main ingestion pipeline. Iterates through all defined schemas, fetches data 
    from the IGDB API using pagination, and updates the watermark state in ADLS.
    
    Pagination logic:
    - Uses offset-based pagination (limit 500 per request).
    - If offset reaches 10,000 (IGDB limit), shifts the query cursor to the max 
      `updated_at` timestamp seen so far and resets the offset to 0.
    """
    tables = _construct_tables_dict(azure_client)

    for Model, watermark in tables.items():
        try:
            # Initialize pagination variables for the current schema
            cursor = watermark
            offset = 0
            max_seen = watermark

            while True:
                # Respect IGDB API rate limits
                bucket.acquire()
                
                # Fetch batch from IGDB
                query = Model.build_query(last_update_value=cursor, offset=offset)
                batch = extract_igdb_data(url=f"{BASE_IGDB_URL}{Model._endpoint}", query=query, timeout=10)
                if not batch:
                    break

                # TODO: Save the raw batch to ADLS (raw/bronze zone)
                
                # Track the latest update timestamp in the current batch
                max_seen = max(r['updated_at'] for r in batch)
                
                # If we received fewer records than the limit, we reached the end of the data
                if len(batch) < 500:
                    break
                    
                offset += 500
                
                # IGDB limits offset pagination to 10,000 records.
                # To bypass this, we shift the cursor to the latest timestamp and reset the offset.
                if offset >= 10000:
                    cursor = max_seen
                    offset = 0

            # Update the in-memory watermark for this model
            tables[Model] = max_seen

            # Persist progress to ADLS after successfully processing each table.
            # This prevents losing progress for all tables if a subsequent one fails.
            final = {cls.__name__: ts for cls, ts in tables.items()}
            write_into_raw(
                azure_client, 
                Containers.Control.value, 
                "watermark.json", 
                json.dumps(final).encode()
            )

        except Exception as e:
            # Log failure and continue with the next table to ensure partial pipeline success
            print(f"Failed to ingest {Model.__name__}: {e}")
            log_to_discord(msg=f"Failed to ingest {Model.__name__}: {e}", level=AlertLevel.ERROR)
            continue