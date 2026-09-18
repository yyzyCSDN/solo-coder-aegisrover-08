import math
from aegisrover.core.types import Pose2, wrap_angle

def update(pose, left_delta, right_delta, wheel_base):
    if wheel_base <= 0:
        raise ValueError('wheel_base')
    ds = (left_delta + right_delta) / 2.0
    dtheta = (right_delta - left_delta) / wheel_base
    if abs(dtheta) < 1e-12:
        return Pose2(pose.x + ds * math.cos(pose.yaw), pose.y + ds * math.sin(pose.yaw), pose.yaw)
    r = ds / dtheta
    nx = pose.x + r * (math.sin(pose.yaw + dtheta) - math.sin(pose.yaw))
    ny = pose.y - r * (math.cos(pose.yaw + dtheta) - math.cos(pose.yaw))
    return Pose2(nx, ny, wrap_angle(pose.yaw + dtheta))
