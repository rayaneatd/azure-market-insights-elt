import os
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, wait_fixed, retry_if_exception_type

# Relative imports — always use relative imports inside a package to avoid
# collisions with Python's built-in modules (e.g. Python has a built-in 'secrets' module)
from ..secrets.project_credentials import (
    dev_TWITCH_CLIENT_ID,  dev_TWITCH_ACCESS_TOKEN,
    prod_TWITCH_CLIENT_ID, prod_TWITCH_ACCESS_TOKEN
)
from .log_messages import log_to_discord, AlertLevel


# ================================================================
# Custom exceptions
# ================================================================

class IGDBApiError(Exception):
    """Base exception for all IGDB API errors."""
    pass

class IGDBClientError(IGDBApiError):
    """
    Raised on 4xx errors (except 429).
    These are logic/caller errors — retrying will never help.
    Ex: 400 bad query syntax, 401 unauthorized, 404 not found.
    """
    pass

class IGDBRateLimitError(IGDBApiError):
    """
    Raised on 429 Too Many Requests.
    Separated from IGDBClientError because 429 IS retryable — we just
    need to wait before retrying (respecting the Retry-After header).
    """
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        # retry_after holds the number of seconds the server asks us to wait
        self.retry_after = retry_after

class IGDBServerError(IGDBApiError):
    """
    Raised on 5xx errors.
    These are server-side errors — potentially transient (overload, restart, etc.)
    so they are safe to retry. We raise a real typed exception instead of converting
    to another exception type, which would corrupt logs and monitoring.
    """
    pass


# ================================================================
# Retry configuration
# ================================================================

def _igdb_wait_strategy(retry_state):
    """
    Custom wait strategy:
    - For 429 errors, respect the Retry-After header if present.
    - For everything else, fall back to exponential backoff.
    """
    exc = retry_state.outcome.exception()

    if isinstance(exc, IGDBRateLimitError) and exc.retry_after is not None:
        # The server explicitly told us how long to wait — always respect it
        return exc.retry_after

    # Default: exponential backoff (1s → 2s → 4s → ... capped at 30s)
    return wait_exponential(multiplier=1, min=1, max=30)(retry_state)


# ================================================================
# API call functions
# ================================================================

@retry(
    # Retry on transient network errors, rate limits (429), and server errors (5xx).
    # IGDBClientError (4xx) is NOT included — those are logic errors, never retry them.
    retry=retry_if_exception_type((
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        IGDBRateLimitError,
        IGDBServerError,
    )),

    # Use our custom wait strategy to handle Retry-After on 429
    wait=_igdb_wait_strategy,

    # Give up after 4 total attempts (1 original + 3 retries)
    stop=stop_after_attempt(4),
)
def extract_igdb_data(url: str, query: str, timeout: int = 10) -> list:
    """
    Make a POST request to the IGDB API using Apicalypse query syntax.

    Automatically retries on transient errors with the correct strategy:
      - Timeout / ConnectionError  → exponential backoff
      - 429 Too Many Requests      → waits for Retry-After header value
      - 5xx Server Error           → exponential backoff

    Credentials and environment are resolved at call time (not at import time)
    to always reflect the current runtime state.

    Args:
        url     (str): IGDB endpoint, ex: "https://api.igdb.com/v4/games"
        query   (str): Apicalypse query, ex: "fields name, rating; limit 10;"
        timeout (int): Request timeout in seconds (default: 10)

    Returns:
        list: Parsed JSON response as a list.

    Raises:
        IGDBClientError:    On unrecoverable 4xx errors (bad query, unauthorized, etc.)
        IGDBRateLimitError: On 429 after all retry attempts are exhausted.
        IGDBServerError:    On 5xx after all retry attempts are exhausted.
        requests.exceptions.Timeout:         On timeout after all retries exhausted.
        requests.exceptions.ConnectionError: On connection failure after all retries.
    """

    # IS_PROD is re-read from the environment at every call, not cached at import time.
    # This is critical: if the env var changes (e.g. during tests or a live switch),
    # importing IS_PROD at module level would silently keep the stale value forever.
    is_prod = os.getenv("ENVIRONMENT", "dev").strip().lower() == "prod"

    # Credentials resolved at call time for the same reason as IS_PROD above
    client_id    = prod_TWITCH_CLIENT_ID    if is_prod else dev_TWITCH_CLIENT_ID
    access_token = prod_TWITCH_ACCESS_TOKEN if is_prod else dev_TWITCH_ACCESS_TOKEN

    # IGDB requires the Twitch Client-ID and a Bearer token for every request
    headers = {
        "Client-ID":     client_id,
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "text/plain"
    }

    try:
        # IGDB uses POST requests: the Apicalypse query is sent as raw body data
        response = requests.post(url, headers=headers, data=query, timeout=timeout)

        # raise_for_status() raises an HTTPError for any 4xx or 5xx response.
        # We then re-map it to our own typed exceptions for precise error handling.
        response.raise_for_status()

        return response.json()

    except requests.exceptions.Timeout:
        # Re-raise as-is — Tenacity will catch it and schedule a retry
        raise

    except requests.exceptions.ConnectionError:
        # Re-raise as-is — Tenacity will catch it and schedule a retry
        raise

    except requests.exceptions.HTTPError as e:
        status = response.status_code

        if status == 429:
            # Read the Retry-After header so we wait exactly as long as the server asks.
            # The header value is in seconds (an integer string, e.g. "5").
            retry_after_raw = response.headers.get("Retry-After")
            retry_after = float(retry_after_raw) if retry_after_raw else None

            log_to_discord(
                f"IGDB rate limit hit (429). Retry-After: {retry_after}s",
                level=AlertLevel.WARNING
            )
            raise IGDBRateLimitError(str(e), retry_after=retry_after)

        if status >= 500:
            # Server-side error — potentially transient, Tenacity will retry
            log_to_discord(f"IGDB server error ({status}): {e}", level=AlertLevel.WARNING)
            raise IGDBServerError(str(e))

        # 4xx (excluding 429) — logic/caller error, retrying is pointless
        log_to_discord(f"IGDB client error ({status}): {e}", level=AlertLevel.ERROR)
        raise IGDBClientError(str(e))

    except requests.exceptions.RequestException as e:
        # Catch-all for any other requests error (DNS failure, SSL error, etc.)
        log_to_discord(f"IGDB request error: {e}", level=AlertLevel.ERROR)
        raise