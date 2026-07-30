# pyrefly: ignore [missing-import]
from .igdb.client import extract_igdb_data

# get the data from the API
data = extract_igdb_data("https://api.igdb.com/v4/games", "fields *; limit 10;")

# print the data (testing)
print(data)


# pagination is done here!!!!!!!!!!!!!