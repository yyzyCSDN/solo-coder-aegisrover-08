import math

def parameterize(points, max_speed, max_accel):
    n = len(points)
    if n == 0:
        return []
    v = [max_speed] * n
    v[0] = 0.0
    v[-1] = 0.0
    for i in range(1, n):
        d = math.dist(points[i - 1], points[i])
        v[i] = min(v[i], math.sqrt(max(0, v[i - 1] ** 2 + 2 * max_accel * d)))
    for i in range(n - 2, -1, -1):
        d = math.dist(points[i], points[i + 1])
        v[i] = min(v[i], math.sqrt(max(0, v[i + 1] ** 2 + 2 * max_accel * d)))
    t = [0.0]
    for i in range(1, n):
        d = math.dist(points[i - 1], points[i])
        denom = v[i - 1] + v[i]
        t.append(t[-1] + (0.0 if d == 0 else 2 * d / denom if denom > 0 else float('inf')))
    return list(zip(t, v))
