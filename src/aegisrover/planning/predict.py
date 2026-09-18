"""Collision checking for swept motion and constant-velocity obstacles.

Checking only the sampled waypoints misses collisions that happen *between* two
waypoints, so every check works on the swept segment. Dynamic obstacles are checked
against the robot's relative motion, which is the only way to notice that two agents
converging head-on are dangerous even though each one alone moves predictably.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

__all__ = ('CircleObstacle', 'Conflict', 'segment_point_distance', 'segment_circles_conflict',
           'swept_path_conflict', 'time_to_collision', 'inflate', 'minkowski_clearance')

Point = tuple[float, float]


@dataclass(frozen=True)
class CircleObstacle:
    x: float
    y: float
    radius: float
    vx: float = 0.0
    vy: float = 0.0

    def at(self, t: float) -> Point:
        return (self.x + self.vx * t, self.y + self.vy * t)


@dataclass(frozen=True)
class Conflict:
    segment: int
    obstacle: int
    distance: float
    point: Point

    def to_dict(self) -> dict:
        return {'segment': self.segment, 'obstacle': self.obstacle,
                'distance': round(self.distance, 6), 'point': [round(v, 6) for v in self.point]}


def segment_point_distance(a: Point, b: Point, p: Point) -> tuple[float, Point]:
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = p[0] - a[0], p[1] - a[1]
    length_sq = vx * vx + vy * vy
    if length_sq <= 1e-18:
        return math.hypot(p[0] - a[0], p[1] - a[1]), a
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / length_sq))
    closest = (a[0] + t * vx, a[1] + t * vy)
    return math.hypot(p[0] - closest[0], p[1] - closest[1]), closest


def segment_circles_conflict(a: Point, b: Point, obstacles: Sequence[CircleObstacle],
                             robot_radius: float) -> Conflict | None:
    for index, obstacle in enumerate(obstacles):
        distance, closest = segment_point_distance(a, b, (obstacle.x, obstacle.y))
        if distance <= robot_radius + obstacle.radius + 1e-12:
            return Conflict(-1, index, distance, closest)
    return None


def swept_path_conflict(path: Sequence[Point], obstacles: Sequence[CircleObstacle],
                        robot_radius: float) -> Conflict | None:
    if robot_radius < 0:
        raise ValueError('robot_radius must not be negative')
    for segment, (a, b) in enumerate(zip(path, path[1:])):
        found = segment_circles_conflict(a, b, obstacles, robot_radius)
        if found is not None:
            return Conflict(segment, found.obstacle, found.distance, found.point)
    return None


def time_to_collision(robot: Point, robot_velocity: Point, obstacle: CircleObstacle, *,
                      horizon: float, robot_radius: float = 0.0) -> tuple[float, float]:
    """Earliest contact time inside ``horizon`` plus the separation at that moment.

    ``-1.0`` as the first element means "no contact inside the window"; the second
    element is then the closest approach distance.
    """
    if horizon <= 0:
        raise ValueError('horizon must be positive')
    dx = robot[0] - obstacle.x
    dy = robot[1] - obstacle.y
    dvx = robot_velocity[0] - obstacle.vx
    dvy = robot_velocity[1] - obstacle.vy
    radius = robot_radius + obstacle.radius
    a = dvx * dvx + dvy * dvy
    b = 2.0 * (dx * dvx + dy * dvy)
    c = dx * dx + dy * dy - radius * radius
    if a <= 1e-18:
        closest = math.hypot(dx, dy)
        return (0.0 if closest <= radius else -1.0, closest)
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        t_closest = max(0.0, min(horizon, -b / (2 * a)))
        return (-1.0, math.hypot(dx + dvx * t_closest, dy + dvy * t_closest))
    root = math.sqrt(discriminant)
    for candidate in ((-b - root) / (2 * a), (-b + root) / (2 * a)):
        if 0.0 <= candidate <= horizon:
            return (candidate, math.hypot(dx + dvx * candidate, dy + dvy * candidate))
    t_closest = max(0.0, min(horizon, -b / (2 * a)))
    return (-1.0, math.hypot(dx + dvx * t_closest, dy + dvy * t_closest))


def inflate(obstacles: Iterable[CircleObstacle], margin: float) -> list[CircleObstacle]:
    if margin < 0:
        raise ValueError('margin must not be negative')
    return [CircleObstacle(o.x, o.y, o.radius + margin, o.vx, o.vy) for o in obstacles]


def minkowski_clearance(path: Sequence[Point], obstacles: Sequence[CircleObstacle]) -> float:
    """Smallest clearance along the path (negative when the path intersects)."""
    best = math.inf
    for a, b in zip(path, path[1:]):
        for obstacle in obstacles:
            distance, _ = segment_point_distance(a, b, (obstacle.x, obstacle.y))
            best = min(best, distance - obstacle.radius)
    return best
