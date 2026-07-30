import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Relative imports — always use relative imports inside a package to avoid
# collisions with Python's built-in modules (e.g. Python has a built-in 'secrets' module)
from ..secrets.project_environment import IS_PROD
from ..secrets.project_credentials import (
    dev_TWITCH_CLIENT_ID,  dev_TWITCH_ACCESS_TOKEN,
    prod_TWITCH_CLIENT_ID, prod_TWITCH_ACCESS_TOKEN
)
from .log_messages import log_to_discord, AlertLevel


# ================================================================
# Retry configuration
# ================================================================

# Only retry on transient network errors (timeout, connection dropped, etc.)
# 4xx errors (bad request, unauthorized, not found) are logic errors — retrying
# them would be pointless since the result will always be the same.
# 5xx errors (server errors) are retried via raise in the except block below.
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)


# ================================================================
# API call functions
# ================================================================

@retry(
    # Only trigger a retry when one of the RETRYABLE_EXCEPTIONS is raised
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),

    # Exponential backoff: wait 1s, then 2s, then 4s, up to 30s max.
    # This avoids hammering an already overloaded server.
    wait=wait_exponential(multiplier=1, min=1, max=30),

    # Give up after 4 total attempts (1 original + 3 retries)
    stop=stop_after_attempt(4),
)
def extract_igdb_data(url: str, query: str, timeout: int = 10) -> list | None:
    """
    Make a POST request to the IGDB API using Apicalypse query syntax.

    Automatically retries on transient network errors (Timeout, ConnectionError)
    with exponential backoff — up to 4 attempts total.

    Credentials are resolved at call time (not at import time) so that any
    environment change or token rotation is always picked up correctly.

    Args:
        url     (str): IGDB endpoint, ex: "https://api.igdb.com/v4/games"
        query   (str): Apicalypse query, ex: "fields name, rating; limit 10;"
        timeout (int): Request timeout in seconds (default: 10)

    Returns:
        list | None: Parsed JSON response as a list, or None on any unrecoverable error.
    """

    # Resolve credentials at call time, not at module import time.
    # This ensures token rotations or environment switches are always reflected.
    client_id    = prod_TWITCH_CLIENT_ID    if IS_PROD else dev_TWITCH_CLIENT_ID
    access_token = prod_TWITCH_ACCESS_TOKEN if IS_PROD else dev_TWITCH_ACCESS_TOKEN

    # IGDB requires the Twitch Client-ID and a Bearer token for every request
    headers = {
        "Client-ID":     client_id,
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "text/plain"
    }

    try:
        # IGDB uses POST requests: the Apicalypse query is sent as raw body data
        response = requests.post(url, headers=headers, data=query, timeout=timeout)

        # raise_for_status() automatically raises an HTTPError for any 4xx or 5xx.
        # If no exception is raised, the response is guaranteed to be 2xx.
        response.raise_for_status()

        return response.json()

    except requests.exceptions.Timeout:
        # Re-raise so Tenacity intercepts it and schedules a retry
        raise

    except requests.exceptions.ConnectionError:
        # Re-raise so Tenacity intercepts it and schedules a retry
        raise

    except requests.exceptions.HTTPError as e:
        if response.status_code >= 500:
            # 5xx = server-side error, potentially transient (overload, restart, etc.)
            # Re-raise so Tenacity can retry it as well
            raise requests.exceptions.ConnectionError(e)

        # 4xx = client-side error (bad query, unauthorized, not found, etc.)
        # Retrying would be pointless — log and return None immediately
        log_to_discord(f"IGDB HTTP {response.status_code}: {e}", level=AlertLevel.ERROR)
        return None

    except requests.exceptions.RequestException as e:
        # Catch-all for any other requests-related error (DNS failure, SSL error, etc.)
        log_to_discord(f"IGDB request error: {e}", level=AlertLevel.ERROR)
        return None