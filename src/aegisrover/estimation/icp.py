import math
from aegisrover.core.types import Vec2, Pose2

def centroid(points):
    n = len(points)
    return Vec2(sum((p.x for p in points)) / n, sum((p.y for p in points)) / n)

def fit_rigid(src, dst):
    if len(src) != len(dst) or len(src) < 2:
        raise ValueError('pairs')
    cs = centroid(src)
    cd = centroid(dst)
    a = b = 0.0
    for p, q in zip(src, dst):
        px, py = (p.x - cs.x, p.y - cs.y)
        qx, qy = (q.x - cd.x, q.y - cd.y)
        a += px * qx + py * qy
        b += px * qy - py * qx
    yaw = math.atan2(b, a)
    c = math.cos(yaw)
    s = math.sin(yaw)
    tx = cd.x - (c * cs.x - s * cs.y)
    ty = cd.y - (s * cs.x + c * cs.y)
    return Pose2(tx, ty, yaw)
