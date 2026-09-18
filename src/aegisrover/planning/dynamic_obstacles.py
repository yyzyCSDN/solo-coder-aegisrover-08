from dataclasses import dataclass

@dataclass(frozen=True)
class MovingObstacle:
    x: float
    y: float
    vx: float
    vy: float
    radius: float

    def at(self, t):
        return (self.x + self.vx * t, self.y + self.vy * t)

def minimum_separation(robot_start, robot_velocity, obstacle, horizon):
    rx, ry = robot_start
    rvx, rvy = robot_velocity
    dx = rx - obstacle.x
    dy = ry - obstacle.y
    dvx = rvx - obstacle.vx
    dvy = rvy - obstacle.vy
    denom = dvx * dvx + dvy * dvy
    t = 0.0 if denom == 0 else max(0.0, min(horizon, -(dx * dvx + dy * dvy) / denom))
    sx = dx + dvx * t
    sy = dy + dvy * t
    return ((sx * sx + sy * sy) ** 0.5, t)
