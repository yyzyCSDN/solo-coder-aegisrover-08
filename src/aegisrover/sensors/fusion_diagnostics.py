import math
import statistics

def weighted_fuse(measurements):
    items = list(measurements)
    total = sum((max(0.0, m['weight']) for m in items))
    if total == 0:
        raise ValueError('weights')
    value = sum((m['value'] * max(0.0, m['weight']) for m in items)) / total
    return value

def freshness_weight(age, half_life):
    if half_life <= 0:
        raise ValueError('half_life')
    return 0.5 ** (max(0.0, age) / half_life)

def agreement_score(values):
    xs = list(map(float, values))
    if len(xs) < 2:
        return 1.0
    center = statistics.median(xs)
    mad = statistics.median((abs(x - center) for x in xs))
    return 1.0 / (1.0 + mad)
