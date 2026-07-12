from azure.identity      import DefaultAzureCredential
from azure.storage.blob  import BlobServiceClient

from src.secrets         import *
from utils.log_messages  import *

# init variables
storage_account_url, account_credentials, blob_storage_client = None

def init_blob_storage_client():
    
    try:
        # setup credentials depending on the project's environment
        if IS_DEV:
            print("project initialized for dev")

            storage_account_url = dev_STORAGE_ACCOUNT_URL
            account_credentials = dev_STORAGE_CONNECTION_STRING
            
        elif IS_PROD or IS_TEST:
            print("project deployed for production" if IS_PROD else "project is being tested")

            storage_account_url = prod_STORAGE_ACCOUNT_URL
            account_credentials = DefaultAzureCredential()
        else:
            raise UnknownEnvironment()
    except UnknownEnvironment as err:
        log_to_discord(str(err), level=AlertLevel.ERROR)
        exit(1)

    # blob service client creation
    blob_storage_client = BlobServiceClient(account_url=storage_account_url, credential=account_credentials)