from .project_environment import (
    # helpers
    IS_DEV, IS_PROD, IS_TEST, 
    
    # for err managment
    UnknownEnvironment
)

from .project_credentials import (
    # azure storage credentials
    dev_STORAGE_ACCOUNT_URL, dev_STORAGE_CONNECTION_STRING, 
    prod_STORAGE_ACCOUNT_URL,
    
    # twitch credentials
    dev_TWITCH_CLIENT_ID, dev_TWITCH_ACCESS_TOKEN,
    prod_TWITCH_CLIENT_ID, prod_TWITCH_ACCESS_TOKEN
)