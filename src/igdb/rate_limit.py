from time import monotonic, sleep
import threading

# this allows us to control the rate of requests to the IGDB API
# IGDB API has a rate limit of 4 requests per second
class TokenBucket:
    def __init__(self, capacity: int, fill_rate: float):
        """Initialize the token bucket.
        
        Args:
            capacity (int): The maximum number of tokens the bucket can hold.
            fill_rate (float): The rate at which tokens are added to the bucket per second.
        """
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.tokens: float = float(capacity)  # float: refill() assigns fractional token counts
        self.last_refill = monotonic()
        self.lock = threading.Lock()

    def _refill(self) -> None:
        """Refill the token bucket based on the time elapsed since the last refill."""
        now = monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
        self.last_refill = now

    def acquire(self, amount: int = 1) -> None:
        """Acquire tokens from the bucket, blocking if necessary.
        
        Args:
            amount (int): The number of tokens to acquire.
        """

        if amount > self.capacity:
            raise ValueError("amount > capacity")
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= amount:
                    self.tokens -= amount
                    return
                wait = (amount - self.tokens) / self.fill_rate
            sleep(wait)