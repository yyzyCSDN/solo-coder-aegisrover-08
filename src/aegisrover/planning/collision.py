import math

def segment_point_distance(a, b, p):
    ax, ay = a
    bx, by = b
    px, py = p
    vx, vy = (bx - ax, by - ay)
    wx, wy = (px - ax, py - ay)
    d = vx * vx + vy * vy
    if d == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / d))
    q = (ax + t * vx, ay + t * vy)
    return math.hypot(px - q[0], py - q[1])

def swept_circle_clear(path, obstacles, radius):
    if radius < 0:
        raise ValueError('radius')
    for a, b in zip(path, path[1:]):
        for ox, oy, oradius in obstacles:
            if segment_point_distance(a, b, (ox, oy)) <= radius + oradius:
                return False
    return True
