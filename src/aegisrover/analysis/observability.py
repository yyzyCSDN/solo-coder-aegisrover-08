import math

def percentile(values, p):
    xs = sorted(map(float, values))
    if not xs:
        return None
    index = min(len(xs) - 1, max(0, round((len(xs) - 1) * p)))
    return xs[index]

def summary(values):
    xs = list(map(float, values))
    return {'count': len(xs), 'min': min(xs) if xs else None, 'max': max(xs) if xs else None, 'mean': sum(xs) / len(xs) if xs else None, 'p95': percentile(xs, 0.95)}

def rate(count, seconds):
    return 0.0 if seconds <= 0 else count / seconds

def error_budget(total, failures, objective):
    allowed = total * (1 - objective)
    remaining = allowed - failures
    return {'allowed': allowed, 'remaining': remaining, 'exhausted': remaining < 0}
