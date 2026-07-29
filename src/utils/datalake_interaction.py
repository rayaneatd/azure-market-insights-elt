from azure.storage.filedatalake import DataLakeServiceClient
from sqlalchemy import create_engine
from .log_messages import log_to_discord, AlertLevel

# ================================================================
# Datalake interaction functions
# ================================================================

    # function to write into the raw layer
def write_into_raw(service_client: DataLakeServiceClient, container, value):
    """
    Write data into either the raw or analytics layer.
    
    Args:
        service_client (DataLakeServiceClient): The datalake service client.
        value: The value to write into the datalake.
    """

    try:
        service_client.get_file_client(container, value)
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
    try:
        service_client.get_file_client(container, value)
    except Exception as err:
        log_to_discord(str(err), level=AlertLevel.ERROR)
        raise


# ================================================================
# Postgres interaction functions
# ================================================================

    # function to write into the analytics layer
def write_into_analytics(engine: create_engine, table_name: str, values):
    """
    Write data into the analytics layer.
    
    Args:
        engine (create_engine): The postgres engine.
        table_name (str): The table name.
        values: The values to write into the table.
    """
    pass

    # function to read from the analytics layer
def read_from_analytics(engine: create_engine, table_name: str):
    """
    Read data from the analytics layer.
    
    Args:
        engine (create_engine): The postgres engine.
        table_name (str): The table name.
    """
    pass

# NOTE: those functions will also be used to interact with the watermark tables/files
# those are still "dumb functions" and that's the point