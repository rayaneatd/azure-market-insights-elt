# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from src.secrets.project_credentials import (
    # dev postgres credentials
    DEV_POSTGRES_USER, 
    DEV_POSTGRES_PASSWORD,
    DEV_POSTGRES_HOST,
    DEV_POSTGRES_PORT,
    DEV_POSTGRES_DB,
    # prod postgres credentials
    PROD_POSTGRES_USER,
    PROD_POSTGRES_PASSWORD,
    PROD_POSTGRES_HOST,
    PROD_POSTGRES_PORT,
    PROD_POSTGRES_DB
)

from src.secrets.project_environment import (
    IS_DEV,
    IS_PROD
)

from src.utils.log_messages import log_to_discord, AlertLevel


# initialize database engine
def init_database_engine() -> Engine | None:
    try:
        if IS_DEV:
            engine: Engine = create_engine(
                f"postgresql+psycopg2://{DEV_POSTGRES_USER}:{DEV_POSTGRES_PASSWORD}@{DEV_POSTGRES_HOST}:{DEV_POSTGRES_PORT}/{DEV_POSTGRES_DB}"
            
            #TODO: add connection pooling
            )
        elif IS_PROD:
            engine: Engine = create_engine(
                f"postgresql+psycopg2://{PROD_POSTGRES_USER}:{PROD_POSTGRES_PASSWORD}@{PROD_POSTGRES_HOST}:{PROD_POSTGRES_PORT}/{PROD_POSTGRES_DB}"
            
            #TODO: add connection pooling
            )
        else:
            raise ValueError("Invalid environment")
        return engine
    except Exception as e:
        log_to_discord(f"Error: {e}", level=AlertLevel.ERROR)
        return None