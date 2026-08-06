from azure.storage.filedatalake import DataLakeServiceClient
from sqlalchemy import create_engine
from .log_messages import log_to_discord, AlertLevel

from enum import Enum

    # Enum classes
class Containers(Enum):
    Control = "control"
    Data    = "data"


# ================================================================
# Datalake interaction functions
# ================================================================

    # function to write into the raw layer
def write_into_raw(service_client: DataLakeServiceClient, container, value, data: bytes):
    """
    Write data into either the raw or analytics layer.

    Args:
        service_client (DataLakeServiceClient): The datalake service client.
        container: The target container (Containers enum or string).
        value: The file path within the container.
        data: The bytes content to upload.
    """
    container_name = container.value if isinstance(container, Enum) else container
    try:
        file_client = service_client.get_file_client(container_name, value)
        file_client.upload_data(data, overwrite=True)
    except Exception as err:
        log_to_discord(str(err), level=AlertLevel.ERROR)
        raise

    # function to read from the raw layer
def read_from_raw(service_client: DataLakeServiceClient, container, value):
    """
    Read data from either the raw or analytics layer.
    
    Args:
        service_client (DataLakeServiceClient): The datalake service client.
        value: The value to read from the datalake.
    """
    container_name = container.value if isinstance(container, Enum) else container
    try:
        file_client = service_client.get_file_client(container_name, value)

        download_stream = file_client.download_file()
        
        return download_stream.readall() #! We want it to return bytes so no UTF 8 conversion plz
    except Exception as err:
        log_to_discord(str(err), level=AlertLevel.ERROR)
        raise


# ================================================================
# Postgres interaction functions
# ================================================================

    # function to write into the analytics layer
def write_into_analytics(engine, table_name: str, values):
    """
    Write data into the analytics layer.
    
    Args:
        engine (create_engine): The postgres engine.
        table_name (str): The table name.
        values: The values to write into the table.
    """
    pass

    # function to read from the analytics layer
def read_from_analytics(engine, table_name: str):
    """
    Read data from the analytics layer.
    
    Args:
        engine (create_engine): The postgres engine.
        table_name (str): The table name.
    """
    pass

# NOTE: those functions will also be used to interact with the watermark tables/files
# those are still "dumb functions" and that's the point