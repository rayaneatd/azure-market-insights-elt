# pyrefly: ignore [missing-import]
from utils.api_calls import extract_igdb_data

# get the data from the API
data = extract_igdb_data("https://api.igdb.com/v4/games", "fields *; limit 10;")

# print the data
print(data)