from dotenv import load_dotenv
import os

load_dotenv()

# ==================================================================
# *********** CREDENTIALS ******************************************
# ==================================================================

    # azure storage credentials
dev_STORAGE_ACCOUNT_URL       = os.getenv("dev_STORAGE_ACCOUNT_URL")
dev_STORAGE_CONNECTION_STRING = os.getenv("dev_STORAGE_CONNECTION_STRING")

prod_STORAGE_ACCOUNT_URL      = os.getenv("prod_STORAGE_ACCOUNT_URL")


    # twitch credentials
TWITCH_CLIENT_ID              = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET          = os.getenv("TWITCH_CLIENT_SECRET")



# ==================================================================
# *********** EXCEPTIONS *******************************************
# ==================================================================

class InvalidStorageAccountURL(Exception):
    " Please check the storage account URL "
    pass

