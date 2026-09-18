import math
from aegisrover.core.types import Vec2, Pose2, wrap_angle

def compose(a: Pose2, b: Pose2) -> Pose2:
    c = math.cos(a.yaw)
    s = math.sin(a.yaw)
    return Pose2(a.x + c * b.x - s * b.y, a.y + s * b.x + c * b.y, wrap_angle(a.yaw + b.yaw))

def inverse(p: Pose2) -> Pose2:
    c = math.cos(p.yaw)
    s = math.sin(p.yaw)
    x = -(c * p.x + s * p.y)
    y = s * p.x - c * p.y
    return Pose2(x, y, wrap_angle(-p.yaw))

def transform_point(frame: Pose2, point: Vec2) -> Vec2:
    c = math.cos(frame.yaw)
    s = math.sin(frame.yaw)
    return Vec2(frame.x + c * point.x - s * point.y, frame.y + s * point.x + c * point.y)

def relative(parent: Pose2, child: Pose2) -> Pose2:
    return compose(inverse(parent), child)

def chain(frames):
    out = Pose2(0, 0, 0)
    for f in frames:
        out = compose(out, f)
    return out
