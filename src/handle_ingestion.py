# pyrefly: ignore [missing-import]
from src.igdb.client import extract_igdb_data
from src.tables_schema import *

from azure.storage.filedatalake import DataLakeServiceClient

# fetch the JSON watermark from ADLS then build the dict automatically
# example :
#    last_update: dict = {
#        "games": 1754361600,
#        "release_dates": 1754361600,
#        "genres": 1754361600,
#        "platforms": 1754361600,
#        "companies": 1754361600
#    }
last_update: dict = {}


# get the data from the API
game_query = GameSchema.build_query(limit=500)
game_data = extract_igdb_data("https://api.igdb.com/v4/games", game_query)

release_dates_query = ReleaseDateSchema.build_query(limit=500)
release_dates_data = extract_igdb_data("https://api.igdb.com/v4/release_dates", release_dates_query)

genre_query = GenreSchema.build_query(limit=500)
genre_data = extract_igdb_data("https://api.igdb.com/v4/genres", genre_query)

platform_query = PlatformSchema.build_query(limit=500)
platform_data = extract_igdb_data("https://api.igdb.com/v4/platforms", platform_query)

company_query = CompanySchema.build_query(limit=500)
company_data = extract_igdb_data("https://api.igdb.com/v4/companies", company_query)


# pagination logic
def _get_watermark(azure_client: DataLakeServiceClient) -> dict:
    return {}

def do_ingestion(azure_client: DataLakeServiceClient):
    pass