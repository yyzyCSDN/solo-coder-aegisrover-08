import math, heapq

def distance_field(width, height, obstacles, resolution):
    inf = float('inf')
    d = [[inf] * width for _ in range(height)]
    q = []
    for x, y in obstacles:
        if 0 <= x < width and 0 <= y < height:
            d[y][x] = 0.0
            heapq.heappush(q, (0.0, x, y))
    moves = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (-1, -1, math.sqrt(2))]
    while q:
        dist, x, y = heapq.heappop(q)
        if dist != d[y][x]:
            continue
        for dx, dy, w in moves:
            nx, ny = (x + dx, y + dy)
            nd = dist + w * resolution
            if 0 <= nx < width and 0 <= ny < height and (nd < d[ny][nx]):
                d[ny][nx] = nd
                heapq.heappush(q, (nd, nx, ny))
    return d

def inflate(field, radius):
    return [[max(0.0, 1 - v / radius) if radius > 0 else 0.0 for v in row] for row in field]
