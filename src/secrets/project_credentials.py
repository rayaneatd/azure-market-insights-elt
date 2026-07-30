# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

# ==================================================================
# *********** DEV CREDENTIALS **************************************
# ==================================================================

    # azure storage credentials
dev_STORAGE_ACCOUNT_URL       = os.getenv("dev_STORAGE_ACCOUNT_URL").upper()
dev_STORAGE_CONNECTION_STRING = os.getenv("dev_STORAGE_CONNECTION_STRING").upper()

    # twitch credentials
dev_TWITCH_CLIENT_ID    = os.getenv("dev_TWITCH_CLIENT_ID").upper()
dev_TWITCH_ACCESS_TOKEN = os.getenv("dev_TWITCH_ACCESS_TOKEN").upper()


# ==================================================================
# *********** PROD CREDENTIALS *************************************
# ==================================================================

    # azure storage credentials
prod_STORAGE_ACCOUNT_URL = os.getenv("prod_STORAGE_ACCOUNT_URL").upper()

    # twitch credentials
prod_TWITCH_CLIENT_ID    = os.getenv("prod_TWITCH_CLIENT_ID").upper()
prod_TWITCH_ACCESS_TOKEN = os.getenv("prod_TWITCH_ACCESS_TOKEN").upper()


# ==================================================================
# *********** EXCEPTIONS *******************************************
# ==================================================================

class InvalidStorageAccountURL(Exception):
    " Please check the storage account URL "
    pass

