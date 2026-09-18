from collections import Counter
import math


def queue_pressure(depth, capacity):
    if capacity <= 0:
        raise ValueError('capacity')
    return max(0.0, depth / capacity)


def deadline_misses(records):
    misses = []
    for record in records:
        deadline = record.get('deadline')
        finish = record.get('finish')
        if deadline is not None and finish is not None and finish > deadline:
            misses.append(record)
    return misses


def lease_utilization(leases, now):
    active = 0
    expired = 0
    for lease in leases:
        if lease.get('expires', 0) > now:
            active += 1
        else:
            expired += 1
    total = active + expired
    return {
        'active': active,
        'expired': expired,
        'ratio': 0.0 if total == 0 else active / total,
    }


def error_distribution(events):
    counts = Counter()
    for event in events:
        if event.get('level') == 'error':
            counts[event.get('code', 'unknown')] += 1
    return dict(counts)


def latency_budget(samples, budget):
    values = sorted(float(x) for x in samples)
    if not values:
        return {'count': 0, 'over': 0, 'p95': None}
    over = sum(1 for value in values if value > budget)
    index = min(len(values) - 1, int((len(values) - 1) * 0.95))
    return {'count': len(values), 'over': over, 'p95': values[index]}


def saturation_ratio(commands, limit):
    if limit <= 0:
        raise ValueError('limit')
    values = list(map(float, commands))
    if not values:
        return 0.0
    saturated = sum(1 for value in values if abs(value) >= limit)
    return saturated / len(values)


def drift_summary(samples):
    values = list(map(float, samples))
    if len(values) < 2:
        return {'span': 0.0, 'slope': 0.0}
    span = values[-1] - values[0]
    slope = span / (len(values) - 1)
    return {'span': span, 'slope': slope}


def scheduler_skew(expected, actual):
    if len(expected) != len(actual):
        raise ValueError('length')
    deltas = [b - a for a, b in zip(expected, actual)]
    if not deltas:
        return {'mean': 0.0, 'max_abs': 0.0}
    return {
        'mean': sum(deltas) / len(deltas),
        'max_abs': max(abs(value) for value in deltas),
    }


def watchdog_headroom(wall_limit, cpu_limit, wall_used, cpu_used):
    return {
        'wall': wall_limit - wall_used,
        'cpu': cpu_limit - cpu_used,
        'exhausted': wall_used > wall_limit or cpu_used > cpu_limit,
    }


def subsystem_health(checks):
    result = []
    for name, ok, detail in checks:
        result.append({'name': name, 'ok': bool(ok), 'detail': detail})
    healthy = all(item['ok'] for item in result)
    return {'ok': healthy, 'checks': result}
