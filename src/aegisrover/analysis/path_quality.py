import math

def length(path):
    return sum((math.dist(a, b) for a, b in zip(path, path[1:])))

def heading_changes(path):
    hs = [math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(path, path[1:])]
    return [(b - a + math.pi) % (2 * math.pi) - math.pi for a, b in zip(hs, hs[1:])]

def curvature_score(path):
    return sum((abs(x) for x in heading_changes(path)))

def clearance_score(path, obstacles):
    vals = []
    for p in path:
        vals.append(min((math.dist(p, (o[0], o[1])) - o[2] for o in obstacles), default=999.0))
    return min(vals, default=999.0)

def report(path, obstacles=()):
    return {'length': length(path), 'turning': curvature_score(path), 'min_clearance': clearance_score(path, obstacles)}
