# pyrefly: ignore [missing-import]
from src.handle_auth import init_datalake_service_client

# authentification is managed only when the program starts
datalake_service_client = init_datalake_service_client()

# full code - orchestration is fully linear
def run_full_pipeline():                                                                                                                                                                                                   
    pass


if __name__ == "__main__":
    run_full_pipeline()