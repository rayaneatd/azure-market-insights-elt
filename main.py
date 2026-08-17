# pyrefly: ignore [missing-import]
from src.datalake_service_client import init_datalake_service_client
from src.database_auth import init_database_engine
from src.utils.log_messages import log_to_discord, AlertLevel  # pyrefly: ignore [missing-import]

from src.handle_ingestion import do_ingestion

# authentification is managed only when the program starts
datalake_service_client = init_datalake_service_client()
database_engine = init_database_engine()

# full code - orchestration is fully linear
def run_full_pipeline():                                                                                                                                                                                                   
    if datalake_service_client is None:
        log_to_discord("Error: Datalake service client not initialized", level=AlertLevel.ERROR)
        return 

    if database_engine is None:
        log_to_discord("Error: Database engine not initialized", level=AlertLevel.ERROR)
        return

    do_ingestion(datalake_service_client)

if __name__ == "__main__":
    run_full_pipeline()