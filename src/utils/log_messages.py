import requests
from enum import Enum

import os
from dotenv import load_dotenv

load_dotenv()

# var
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# enum
class AlertLevel(Enum):
    ERROR   = 'ERROR'
    WARNING = 'WARNING'
    INFO    = 'INFO'

# functions
def log_to_discord(msg: str, level: AlertLevel):
    
    data = {
        "text": f'[{level.value}] {msg} - @everyone'
    }

    response = requests.post(DISCORD_WEBHOOK_URL, json=data)

        #? in case the request didn't make it
    if response.status_code != 204: 
        print(f"Erreur envoi Discord: {response.text}")