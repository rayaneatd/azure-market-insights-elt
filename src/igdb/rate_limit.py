from time import time

# this allows us to control the rate of requests to the IGDB API
# IGDB API has a rate limit of 10 requests per second
class TokenBucket:
    def __init__(self, capacity: int, fill_rate: float):
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.tokens: float = float(capacity)  # float: refill() assigns fractional token counts
        self.last_refill = time()

    def refill(self):
        now = time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
        self.last_refill = now

    def consume(self, amount: int) -> bool:
        self.refill()
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False