import requests
from enum import Enum

import os
from dotenv import load_dotenv

load_dotenv()

# webhook url for discord that we get from the .env file
DISCORD_WEBHOOK_URL = str(os.getenv("DISCORD_WEBHOOK_URL"))

# an Enum for alert levels (we can add more levels if needed)
class AlertLevel(Enum):
    ERROR   = 'ERROR'
    WARNING = 'WARNING'
    INFO    = 'INFO'

# function to log messages to discord
# (we can also use slack instead, we just need to refactor this function)
def log_to_discord(msg: str, level: AlertLevel):
    
    data = {
        "text": f'[{level.value}] {msg} - @everyone'
    }

    response = requests.post(DISCORD_WEBHOOK_URL, json=data)

        #? in case the request didn't make it
    if response.status_code != 204: 
        print(f"Erreur envoi Discord: {response.text}")