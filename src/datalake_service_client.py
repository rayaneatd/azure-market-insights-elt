# pyrefly: ignore [missing-import]
from azure.identity             import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

from .secrets                   import *
from .utils.log_messages        import *

# init variable
datalake_service_client = None

# function
def init_datalake_service_client() -> DataLakeServiceClient | None:
    """
    Initialize the datalake service client depending on the project's environment.
    
    Returns:
        DataLakeServiceClient | None: The datalake service client.
    """
    try:
        # setup credentials depending on the project's environment
        if IS_DEV:
            print("project initialized for dev")
            
                # blob service client creation
            return DataLakeServiceClient.from_connection_string(dev_STORAGE_CONNECTION_STRING)

        elif IS_PROD or IS_TEST:
            print("project deployed for production" if IS_PROD else "project is being tested")

                # blob service client creation
            return DataLakeServiceClient(account_url=prod_STORAGE_ACCOUNT_URL, credential=DefaultAzureCredential())
        else:
            raise UnknownEnvironment("Unknown Environment.")
    except UnknownEnvironment as err:
        log_to_discord(str(err), level=AlertLevel.ERROR)
        raise