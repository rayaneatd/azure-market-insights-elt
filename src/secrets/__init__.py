from .project_environment import (
    # helpers
    IS_DEV, IS_PROD, IS_TEST, 
    
    # for err managment
    UnknownEnvironment
)

from .project_credentials import (
    dev_STORAGE_ACCOUNT_URL, dev_STORAGE_CONNECTION_STRING, prod_STORAGE_ACCOUNT_URL
)