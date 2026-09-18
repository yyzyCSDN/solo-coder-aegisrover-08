"""Path smoothing and time parameterisation with explicit feasibility reports.

Smoothing must keep the first and last waypoint exactly: a smoothed path that starts
at the second waypoint leaves the robot short of its real departure point. Time
parameterisation then assigns a speed profile that starts and ends at rest while
respecting a maximum speed and a maximum acceleration everywhere.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

__all__ = ('TrajectorySample', 'Trajectory', 'smooth', 'time_parameterize', 'polyline_length')

Point = tuple[float, float]


@dataclass(frozen=True)
class TrajectorySample:
    t: float
    s: float
    v: float
    point: Point


@dataclass(frozen=True)
class Trajectory:
    samples: tuple[TrajectorySample, ...]
    duration: float
    max_speed: float
    max_accel: float
    feasible: bool
    violations: tuple[str, ...] = ()

    def at(self, t: float) -> TrajectorySample:
        if not self.samples:
            raise ValueError('empty trajectory')
        for sample in self.samples:
            if sample.t >= t:
                return sample
        return self.samples[-1]

    def to_dict(self) -> dict:
        return {'duration': self.duration, 'max_speed': self.max_speed, 'max_accel': self.max_accel,
                'feasible': self.feasible, 'violations': list(self.violations),
                'samples': [{'t': round(s.t, 6), 's': round(s.s, 6), 'v': round(s.v, 6),
                             'point': [round(s.point[0], 6), round(s.point[1], 6)]} for s in self.samples]}


def polyline_length(points: Sequence[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def _catmull_rom(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    t2, t3 = t * t, t * t * t

    def axis(a: float, b: float, c: float, d: float) -> float:
        return 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)

    return (axis(p0[0], p1[0], p2[0], p3[0]), axis(p0[1], p1[1], p2[1], p3[1]))


def smooth(points: Sequence[Point], *, per_segment: int = 8, preserve_endpoints: bool = True) -> list[Point]:
    """Catmull-Rom smoothing that keeps the original first and last waypoint."""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 3 or per_segment < 1:
        return pts
    extended = [pts[0], *pts, pts[-1]]
    out: list[Point] = [pts[0]] if preserve_endpoints else []
    for i in range(1, len(extended) - 2):
        for k in range(per_segment):
            out.append(_catmull_rom(extended[i - 1], extended[i], extended[i + 1], extended[i + 2],
                                    k / per_segment))
    out.append(pts[-1])
    if preserve_endpoints:
        if math.dist(out[0], pts[0]) > 1e-9 or math.dist(out[-1], pts[-1]) > 1e-9:
            raise AssertionError('smoothing moved an endpoint')
    return out


def time_parameterize(points: Sequence[Point], *, max_speed: float, max_accel: float,
                      start_speed: float = 0.0, end_speed: float = 0.0) -> Trajectory:
    if max_speed <= 0 or max_accel <= 0:
        raise ValueError('max_speed and max_accel must be positive')
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        sample = TrajectorySample(0.0, 0.0, 0.0, pts[0]) if pts else TrajectorySample(0.0, 0.0, 0.0, (0.0, 0.0))
        return Trajectory((sample,), 0.0, max_speed, max_accel, True)
    distances = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    cumulative = [0.0]
    for distance in distances:
        cumulative.append(cumulative[-1] + distance)
    speeds = [max_speed] * len(pts)
    speeds[0] = min(max_speed, start_speed)
    speeds[-1] = min(max_speed, end_speed)
    for i in range(1, len(pts)):
        speeds[i] = min(speeds[i], math.sqrt(max(0.0, speeds[i - 1] ** 2 + 2 * max_accel * distances[i - 1])))
    for i in range(len(pts) - 2, -1, -1):
        speeds[i] = min(speeds[i], math.sqrt(max(0.0, speeds[i + 1] ** 2 + 2 * max_accel * distances[i])))
    times = [0.0]
    for i in range(1, len(pts)):
        average = (speeds[i - 1] + speeds[i]) / 2.0
        if distances[i - 1] <= 1e-12 or average <= 1e-9:
            times.append(times[-1])
        else:
            times.append(times[-1] + distances[i - 1] / average)
    samples = tuple(TrajectorySample(times[i], cumulative[i], speeds[i], pts[i]) for i in range(len(pts)))
    violations = _violations(samples, distances, max_speed, max_accel)
    return Trajectory(samples, times[-1], max_speed, max_accel, not violations, violations)


def _violations(samples: Sequence[TrajectorySample], distances: Sequence[float],
                max_speed: float, max_accel: float) -> tuple[str, ...]:
    problems: list[str] = []
    for index, sample in enumerate(samples):
        if sample.v > max_speed + 1e-9:
            problems.append(f'speed[{index}]={sample.v:.6f}>{max_speed}')
        if index and sample.t < samples[index - 1].t - 1e-12:
            problems.append(f'time[{index}] not monotonic')
    for index, distance in enumerate(distances):
        if distance <= 1e-12:
            continue
        a, b = samples[index], samples[index + 1]
        accel = abs(b.v * b.v - a.v * a.v) / (2.0 * distance)
        if accel > max_accel + 1e-6:
            problems.append(f'accel[{index}]={accel:.6f}>{max_accel}')
    return tuple(problems)
