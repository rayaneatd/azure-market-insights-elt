from azure.identity      import DefaultAzureCredential
from azure.storage.blob  import BlobServiceClient

from src.secrets         import *
from utils.log_messages  import *

# init variable
blob_storage_client = None

# function
def init_blob_storage_client():
    
    try:
        # setup credentials depending on the project's environment
        if IS_DEV:
            print("project initialized for dev")
            
                # blob service client creation
            return BlobServiceClient.from_connection_string(dev_STORAGE_CONNECTION_STRING)

        elif IS_PROD or IS_TEST:
            print("project deployed for production" if IS_PROD else "project is being tested")

                # blob service client creation
            return BlobServiceClient(account_url=prod_STORAGE_ACCOUNT_URL, credential=DefaultAzureCredential())
        else:
            raise UnknownEnvironment("Unknown Environment.")
    except UnknownEnvironment as err:
        log_to_discord(str(err), level=AlertLevel.ERROR)
        exit(1)