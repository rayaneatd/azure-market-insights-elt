import os 
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENVIRONMENT = str(os.getenv("ENVIRONMENT")).upper()

    # Helpers
IS_DEV  = PROJECT_ENVIRONMENT == "DEV"
IS_PROD = PROJECT_ENVIRONMENT in ("PROD", "PRODUCTION")
IS_TEST = PROJECT_ENVIRONMENT == "TEST"

    # Exception 
class UnknownEnvironment(Exception):
    """
    Invalid project environment. Please check the 'ENVIRONMENT' variable in case someone made a typo.
    """
    pass