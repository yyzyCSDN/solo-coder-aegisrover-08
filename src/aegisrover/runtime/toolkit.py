from dataclasses import dataclass
import math

@dataclass
class Lease:
    owner: str
    expires: float
    generation: int = 1

    def valid(self, now):
        return now < self.expires

@dataclass
class CircuitBreaker:
    threshold: int = 3
    failures: int = 0
    open_until: float = 0.0

    def allow(self, now):
        return now >= self.open_until

    def success(self):
        self.failures = 0
        self.open_until = 0.0

    def failure(self, now, cooldown):
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until = now + cooldown

def bounded_queue_push(queue, item, limit):
    queue.append(item)
    while len(queue) > limit:
        queue.pop(0)
    return queue

def exponential_backoff(attempt, base=0.1, cap=30.0):
    return min(cap, base * 2 ** max(0, attempt))

def jittered_backoff(attempt, random_value, base=0.1, cap=30.0):
    delay = exponential_backoff(attempt, base, cap)
    return delay * (0.5 + random_value)

def renew_lease(lease, owner, now, duration):
    if lease.owner != owner or not lease.valid(now):
        raise ValueError('not holder')
    lease.expires = now + duration
    lease.generation += 1
    return lease

def memory_budget(items, size_of, limit):
    total = 0
    accepted = []
    for item in items:
        size = size_of(item)
        if total + size > limit:
            break
        accepted.append(item)
        total += size
    return (accepted, total)
