# pyrefly: ignore [missing-import]
from src.igdb.client import extract_igdb_data
from src.tables_schema import *

from azure.storage.filedatalake import DataLakeServiceClient
from src.utils.datalake_interaction import (
    read_from_raw,
    write_into_raw,
    Containers
)
import json

# fetch the JSON watermark from ADLS then build the dict automatically
# example :
#    last_update: dict = {
#        "games": 1754361600,
#        "release_dates": 1754361600,
#        "genres": 1754361600,
#        "platforms": 1754361600,
#        "companies": 1754361600
#    }


# pagination logic
def _construct_tables_dict(azure_client: DataLakeServiceClient) -> dict[type, int]:
    """
    Automatically manages the watermark state on each invocation:
    - Performs 1 systematic read from ADLS.
    - Performs 1 conditional write only if new tables are detected.
    - Initializes missing tables with their default `_starting_point`.

    Output:
        {ClassObject: last_updated_at_timestamp}
    """
    defined_classes: list[type] = BaseIGDBSchema.__subclasses__()

    # Single ADLS read
    raw = read_from_raw(azure_client, Containers.Control.value, "watermark.json")
    watermark_str: dict = json.loads(raw) if raw else {}

    # Detect tables missing from the watermark JSON
    missing = [cls for cls in defined_classes if cls.__name__ not in watermark_str]

    if missing:
        for cls in missing:
            watermark_str[cls.__name__] = cls._starting_point
        # Single ADLS write (only if needed)
        write_into_raw(azure_client, Containers.Control.value, "watermark.json", json.dumps(watermark_str).encode())

    # Return dictionary with class objects as keys (not strings)
    return {cls: watermark_str[cls.__name__] for cls in defined_classes}



def do_ingestion(azure_client: DataLakeServiceClient):
    
    tables = _construct_tables_dict(azure_client)

    for Class in BaseIGDBSchema.__subclasses__():
        endpoint = f"{BASE_IGDB_URL}{Class._endpoint}"

        print(f"{endpoint}: {tables[Class]}\n")

        # pagination logic bla bla
        
