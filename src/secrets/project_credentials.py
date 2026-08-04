from dotenv import load_dotenv
import os

load_dotenv()

# ==================================================================
# *********** CREDENTIALS ******************************************
# ==================================================================

    # azure storage credentials
dev_STORAGE_ACCOUNT_URL       = str(os.getenv("dev_STORAGE_ACCOUNT_URL"))
dev_STORAGE_CONNECTION_STRING = str(os.getenv("dev_STORAGE_CONNECTION_STRING"))

prod_STORAGE_ACCOUNT_URL      = str(os.getenv("prod_STORAGE_ACCOUNT_URL"))


    # twitch credentials
TWITCH_CLIENT_ID              = str(os.getenv("TWITCH_CLIENT_ID"))
TWITCH_CLIENT_SECRET          = str(os.getenv("TWITCH_CLIENT_SECRET"))



# ==================================================================
# *********** EXCEPTIONS *******************************************
# ==================================================================

class InvalidStorageAccountURL(Exception):
    " Please check the storage account URL "
    pass

