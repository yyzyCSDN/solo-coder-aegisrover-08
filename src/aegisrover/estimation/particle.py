import bisect, random

def normalize_weights(weights):
    s = sum(weights)
    if s <= 0:
        return [1 / len(weights)] * len(weights)
    return [w / s for w in weights]

def systematic_resample(particles, weights, rng=None):
    rng = rng or random.Random()
    weights = normalize_weights(weights)
    n = len(particles)
    c = []
    total = 0.0
    for w in weights:
        total += w
        c.append(total)
    start = rng.random() / n
    out = []
    j = 0
    for i in range(n):
        u = start + i / n
        while j < n - 1 and u > c[j]:
            j += 1
        out.append(particles[j])
    return out

def effective_sample_size(weights):
    w = normalize_weights(weights)
    return 1 / sum((x * x for x in w))
