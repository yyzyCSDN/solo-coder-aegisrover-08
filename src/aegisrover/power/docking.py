import math
from aegisrover.core.types import Pose2, wrap_angle

def docking_error(robot: Pose2, dock: Pose2):
    dx = dock.x - robot.x
    dy = dock.y - robot.y
    c = math.cos(-dock.yaw)
    s = math.sin(-dock.yaw)
    longitudinal = c * dx - s * dy
    lateral = s * dx + c * dy
    heading = wrap_angle(robot.yaw - dock.yaw)
    return (longitudinal, lateral, heading)

def acceptable(robot, dock, long_tol, lat_tol, yaw_tol):
    a, b, c = docking_error(robot, dock)
    return abs(a) <= long_tol and abs(b) <= lat_tol and (abs(c) <= yaw_tol)
