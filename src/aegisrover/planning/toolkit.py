import heapq
import math

def path_cost(path, edge_cost):
    return sum((edge_cost(a, b) for a, b in zip(path, path[1:])))

def reconstruct(parent, goal):
    out = [goal]
    while parent.get(out[-1]) is not None:
        out.append(parent[out[-1]])
    return list(reversed(out))

def dijkstra(start, neighbors, cost):
    q = [(0.0, start)]
    dist = {start: 0.0}
    parent = {start: None}
    while q:
        d, node = heapq.heappop(q)
        if d != dist[node]:
            continue
        for nxt in neighbors(node):
            nd = d + cost(node, nxt)
            if nd < dist.get(nxt, float('inf')):
                dist[nxt] = nd
                parent[nxt] = node
                heapq.heappush(q, (nd, nxt))
    return (dist, parent)

def nearest_path_point(path, point):
    best = None
    best_d = float('inf')
    for i, p in enumerate(path):
        d = math.dist(p, point)
        if d < best_d:
            best = i
            best_d = d
    return (best, best_d)

def shortcut(path, clear):
    if len(path) < 3:
        return list(path)
    out = [path[0]]
    i = 0
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1 and (not clear(path[i], path[j])):
            j -= 1
        out.append(path[j])
        i = j
    return out

def resample(path, spacing):
    from aegisrover.geometry.toolkit import sample_polyline
    return sample_polyline(path, spacing)

def heading_profile(path):
    return [math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(path, path[1:])]

def turning_angles(path):
    headings = heading_profile(path)
    return [(b - a + math.pi) % (2 * math.pi) - math.pi for a, b in zip(headings, headings[1:])]
