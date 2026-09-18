from dataclasses import dataclass, field
import random
import math

@dataclass
class Scenario:
    name: str
    duration: float
    seed: int
    events: list = field(default_factory=list)

    def add_event(self, time, kind, payload):
        if not 0 <= time <= self.duration:
            raise ValueError('time')
        self.events.append((float(time), kind, dict(payload)))
        self.events.sort(key=lambda x: x[0])

def seed_stream(seed, count):
    rng = random.Random(seed)
    return [rng.random() for _ in range(count)]

def piecewise_constant(points, t):
    if not points:
        raise ValueError('points')
    value = points[0][1]
    for time, candidate in points:
        if time > t:
            break
        value = candidate
    return value

def piecewise_linear(points, t):
    if not points:
        raise ValueError('points')
    if t <= points[0][0]:
        return points[0][1]
    for a, b in zip(points, points[1:]):
        if a[0] <= t <= b[0]:
            f = (t - a[0]) / (b[0] - a[0])
            return a[1] + f * (b[1] - a[1])
    return points[-1][1]

def poisson_times(rate, duration, seed):
    if rate <= 0:
        return []
    rng = random.Random(seed)
    t = 0.0
    out = []
    while True:
        t += rng.expovariate(rate)
        if t > duration:
            return out
        out.append(t)

def bounded_random_walk(start, steps, sigma, low, high, seed):
    rng = random.Random(seed)
    out = [start]
    value = start
    for _ in range(steps):
        value = max(low, min(high, value + rng.gauss(0, sigma)))
        out.append(value)
    return out
