import random
import requests
from .auth import TwitchAuth
from email.utils import parsedate_to_datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..utils.log_messages import log_to_discord, AlertLevel


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
    - For everything else, fall back to exponential backoff with jitter.
    
    Jitter is added even on Retry-After to prevent the thundering herd problem:
    if 50 workers all hit 429 at the same moment, they all receive the same
    Retry-After value and would re-DDoS IGDB simultaneously without it.
    """
    exc = retry_state.outcome.exception()

    if isinstance(exc, IGDBRateLimitError) and exc.retry_after is not None:
        # Always respect Retry-After, but add a small random jitter to spread
        # retries across time when many workers are throttled simultaneously.
        return exc.retry_after + random.uniform(0, 1)

    # Default: exponential backoff (1s → 2s → 4s → ... capped at 30s) + jitter
    return wait_exponential(multiplier=1, min=1, max=30)(retry_state) + random.uniform(0, 1)


# ================================================================
# API call functions
# ================================================================

twitch_auth = TwitchAuth()

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
    
    # If the exception is not one of the retryable exceptions, re-raise it
    reraise=True
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

    # Credentials resolved at call time for the same reason as IS_PROD above
    # IGDB requires the Twitch Client-ID and a Bearer token for every request
    headers = {
        "Client-ID":     twitch_auth.client_id,
        "Authorization": f"Bearer {twitch_auth.get_access_token()}",
        "Content-Type":  "text/plain"
    }

    response: requests.Response | None = None
    try:
        # IGDB uses POST requests: the Apicalypse query is sent as raw body data
        response = requests.post(url, headers=headers, data=query, timeout=timeout)

        # raise_for_status() raises an HTTPError for any 4xx or 5xx response.
        # We then re-map it to our own typed exceptions for precise error handling.
        response.raise_for_status()

        try:
            return response.json()
        except requests.exceptions.JSONDecodeError as e:
            # The server returned a 2xx but not valid JSON (e.g. empty body, HTML error page).
            # Wrap it in a typed exception so callers don't have to handle an untyped JSONDecodeError.
            log_to_discord(f"IGDB returned invalid JSON: {e}", level=AlertLevel.ERROR)
            raise IGDBApiError(f"Invalid JSON response from IGDB: {e}") from e

    except requests.exceptions.Timeout:
        # Re-raise as-is — Tenacity will catch it and schedule a retry
        raise

    except requests.exceptions.ConnectionError:
        # Re-raise as-is — Tenacity will catch it and schedule a retry
        raise

    except requests.exceptions.HTTPError as e:
        assert response is not None  # response is always set before raise_for_status()
        status = response.status_code

        if status == 429:
            # Read the Retry-After header so we wait exactly as long as the server asks.
            # The header can be either:
            #   - a number of seconds: "5"   → we try float() first
            #   - an HTTP date string:  "Wed, 30 Jul 2026 01:30:00 GMT" → we parse it
            retry_after_raw = response.headers.get("Retry-After")
            retry_after: float | None = None
            if retry_after_raw:
                try:
                    # Case 1: header is a plain number of seconds (most common)
                    retry_after = float(retry_after_raw)
                except ValueError:
                    try:
                        # Case 2: header is an HTTP date — compute remaining seconds
                        from datetime import datetime, timezone
                        target = parsedate_to_datetime(retry_after_raw)
                        retry_after = max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
                    except Exception:
                        # If all parsing fails, fall back to None and let exponential backoff handle it
                        retry_after = None

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
        log_to_discord(f"IGDB client error ({status}): {e} | Body: {response.text}", level=AlertLevel.ERROR)
        raise IGDBClientError(str(e))

    except requests.exceptions.RequestException as e:
        # Catch-all for any other requests error (DNS failure, SSL error, etc.)
        log_to_discord(f"IGDB request error: {e}", level=AlertLevel.ERROR)
        raise