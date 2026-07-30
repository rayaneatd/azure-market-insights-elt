# pyrefly: ignore [missing-import]
from src.datalake_service_client import init_datalake_service_client
from src.utils.log_messages import log_to_discord, AlertLevel  # pyrefly: ignore [missing-import]

# authentification is managed only when the program starts
datalake_service_client = init_datalake_service_client()

# full code - orchestration is fully linear
def run_full_pipeline():                                                                                                                                                                                                   
    if datalake_service_client is None:
        log_to_discord("Error: Datalake service client not initialized", level=AlertLevel.ERROR)
        return
    



if __name__ == "__main__":
    run_full_pipeline()