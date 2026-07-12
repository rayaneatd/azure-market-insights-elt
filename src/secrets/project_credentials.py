from dotenv import load_dotenv
import os

load_dotenv()

# dev credentials
dev_STORAGE_ACCOUNT_URL = os.getenv("dev_STORAGE_ACCOUNT_URL").upper()
dev_STORAGE_CONNECTION_STRING = os.getenv("dev_STORAGE_CONNECTION_STRING").upper()

# prod credentials
prod_STORAGE_ACCOUNT_URL = os.getenv("prod_STORAGE_ACCOUNT_URL").upper()

# Exception
class InvalidStorageAccountURL(Exception):
    " Please check the storage account URL "
    pass

