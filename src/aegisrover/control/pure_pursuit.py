import math
from aegisrover.core.types import Pose2

def choose_lookahead(path, pose, distance):
    if distance <= 0:
        raise ValueError('distance')
    traveled = 0.0
    prev = (pose.x, pose.y)
    for p in path:
        seg = math.dist(prev, p)
        traveled += seg
        if traveled >= distance:
            return p
        prev = p
    return path[-1] if path else (pose.x, pose.y)

def curvature_to_target(pose, target, lookahead):
    dx = target[0] - pose.x
    dy = target[1] - pose.y
    c = math.cos(-pose.yaw)
    s = math.sin(-pose.yaw)
    local_y = s * dx + c * dy
    return 2 * local_y / (lookahead * lookahead)
