class TokenBucket:

    def __init__(self, rate, burst, now=0):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.time = now

    def allow(self, now, cost=1):
        self.tokens = min(self.burst, self.tokens + max(0, now - self.time) * self.rate)
        self.time = max(self.time, now)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False
