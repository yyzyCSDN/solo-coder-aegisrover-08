"""Waypoint execution with geofence supervision.

Two failure modes are covered here. A concave geofence must be evaluated against its
real boundary — a sampling-only check between two points happily walks through the
notch of an L-shaped exclusion zone. And a mission must not be reported as completed
while waypoints are still outstanding, even if the operator presses "complete".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

__all__ = ('Geofence', 'WaypointRunner', 'MissionExecution', 'ExecutionError')

Point = tuple[float, float]


class ExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Geofence:
    """Closed polygon with a membership test that handles concave shapes."""

    polygon: tuple[Point, ...]
    margin: float = 0.0

    def __post_init__(self):
        if len(self.polygon) < 3:
            raise ExecutionError('a geofence needs at least three points')
        if self.margin < 0:
            raise ExecutionError('margin must not be negative')

    def contains(self, point: Point) -> bool:
        x, y = point
        inside = False
        n = len(self.polygon)
        for i in range(n):
            x1, y1 = self.polygon[i]
            x2, y2 = self.polygon[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xi = (x2 - x1) * (y - y1) / (y2 - y1) + x1
                if x < xi:
                    inside = not inside
        if inside:
            return True
        if self.margin > 0:
            return self._distance_to_boundary(point) <= self.margin
        return False

    def segment_inside(self, a: Point, b: Point) -> bool:
        """True when the whole segment stays inside the fence.

        Endpoints inside is not enough: a segment can leave through the notch of a
        concave polygon and come back. Every edge crossing is therefore checked
        against the fence boundary.
        """
        if not (self.contains(a) and self.contains(b)):
            return False
        edges = list(zip(self.polygon, self.polygon[1:] + (self.polygon[0],)))
        for p, q in edges:
            if _segments_cross(a, b, p, q):
                return False
        midpoint = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        return self.contains(midpoint)

    def violations(self, path: Sequence[Point]) -> list[tuple[int, Point]]:
        out: list[tuple[int, Point]] = []
        for index, (a, b) in enumerate(zip(path, path[1:])):
            if not self.segment_inside(a, b):
                out.append((index, b))
        return out

    def _distance_to_boundary(self, point: Point) -> float:
        best = math.inf
        n = len(self.polygon)
        for i in range(n):
            a = self.polygon[i]
            b = self.polygon[(i + 1) % n]
            best = min(best, _point_segment_distance(point, a, b))
        return best


@dataclass
class WaypointRunner:
    waypoints: Sequence[Point]
    tolerance: float = 0.5
    index: int = 0
    skipped: list[Point] = field(default_factory=list)

    def __post_init__(self):
        self.waypoints = tuple((float(x), float(y)) for x, y in self.waypoints)
        if self.tolerance <= 0:
            raise ExecutionError('tolerance must be positive')

    @property
    def current(self) -> Point | None:
        return self.waypoints[self.index] if self.index < len(self.waypoints) else None

    @property
    def done(self) -> bool:
        return self.index >= len(self.waypoints)

    def advance(self, position: Point) -> int:
        while self.index < len(self.waypoints):
            target = self.waypoints[self.index]
            if math.dist(position, target) <= self.tolerance:
                self.index += 1
                continue
            for later in range(self.index + 1, len(self.waypoints)):
                if math.dist(position, self.waypoints[later]) <= self.tolerance:
                    self.skipped.extend(self.waypoints[self.index:later])
                    self.index = later + 1
                    break
            else:
                break
            continue
        return self.index

    def remaining_distance(self, position: Point) -> float:
        if self.done:
            return 0.0
        total = math.dist(position, self.waypoints[self.index])
        for a, b in zip(self.waypoints[self.index:], self.waypoints[self.index + 1:]):
            total += math.dist(a, b)
        return total

    def progress(self) -> float:
        if not self.waypoints:
            return 1.0
        return self.index / len(self.waypoints)


@dataclass
class MissionExecution:
    mission_id: str
    runner: WaypointRunner
    fence: Geofence | None = None
    state: str = 'idle'
    events: list[dict] = field(default_factory=list)
    abort_reason: str | None = None

    def start(self, position: Point) -> str:
        if self.state != 'idle':
            raise ExecutionError(f'cannot start from {self.state}')
        if not self.runner.waypoints:
            raise ExecutionError('mission has no waypoints')
        if self.fence is not None and not self.fence.contains(position):
            raise ExecutionError('start position is outside the geofence')
        if self.fence is not None:
            path = (position, *self.runner.waypoints)
            if self.fence.violations(path):
                raise ExecutionError('planned route leaves the geofence')
        self._log('start', {'position': position})
        self.state = 'running'
        return self.state

    def tick(self, position: Point) -> str:
        if self.state != 'running':
            return self.state
        if self.fence is not None and not self.fence.contains(position):
            self.abort('left the geofence')
            return self.state
        previous = self.runner.index
        self.runner.advance(position)
        if self.runner.index != previous:
            self._log('waypoint', {'index': self.runner.index, 'skipped': len(self.runner.skipped)})
        if self.runner.done:
            self.state = 'completed'
            self._log('complete', {'skipped': len(self.runner.skipped)})
        return self.state

    def pause(self) -> str:
        if self.state != 'running':
            raise ExecutionError(f'cannot pause from {self.state}')
        self.state = 'paused'
        self._log('pause', {})
        return self.state

    def resume(self) -> str:
        if self.state != 'paused':
            raise ExecutionError(f'cannot resume from {self.state}')
        self.state = 'running'
        self._log('resume', {})
        return self.state

    def complete(self) -> str:
        if self.state in ('completed', 'aborted'):
            return self.state
        if not self.runner.done:
            raise ExecutionError('waypoints still outstanding')
        self.state = 'completed'
        self._log('complete', {})
        return self.state

    def abort(self, reason: str) -> str:
        if self.state in ('completed', 'aborted'):
            return self.state
        self.state = 'aborted'
        self.abort_reason = reason
        self._log('abort', {'reason': reason})
        return self.state

    def summary(self) -> dict:
        return {'mission_id': self.mission_id, 'state': self.state,
                'progress': round(self.runner.progress(), 6),
                'skipped': len(self.runner.skipped), 'events': len(self.events),
                'abort_reason': self.abort_reason}

    def _log(self, kind: str, payload: dict) -> None:
        self.events.append({'event': kind, **payload})


def _point_segment_distance(point: Point, a: Point, b: Point) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = point[0] - a[0], point[1] - a[1]
    length_sq = vx * vx + vy * vy
    if length_sq <= 1e-18:
        return math.hypot(wx, wy)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / length_sq))
    return math.hypot(wx - t * vx, wy - t * vy)


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    if (o1 == 0 and _on_segment(a, b, c)) or (o2 == 0 and _on_segment(a, b, d)):
        return True
    if (o3 == 0 and _on_segment(c, d, a)) or (o4 == 0 and _on_segment(c, d, b)):
        return True
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return (min(a[0], b[0]) - 1e-12 <= p[0] <= max(a[0], b[0]) + 1e-12
            and min(a[1], b[1]) - 1e-12 <= p[1] <= max(a[1], b[1]) + 1e-12)
