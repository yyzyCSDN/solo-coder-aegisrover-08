"""Control loop building blocks: PID with anti-windup, actuator limits, pure pursuit.

Three details decide whether a controller behaves on real hardware. The integrator
must not keep accumulating while the actuator is saturated (anti-windup), a slew
limit must be expressed in units per second rather than per loop iteration (or
changing the loop rate silently changes the robot), and the lateral error sign must
match the robot frame so a target on the left commands a left turn.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from aegisrover.core.types import Pose2

__all__ = ('PID', 'ActuatorLimits', 'limit_command', 'limit_pair', 'GainSchedule',
           'pure_pursuit_curvature', 'lateral_error')


@dataclass
class PID:
    kp: float
    ki: float
    kd: float
    minimum: float = -math.inf
    maximum: float = math.inf
    integral: float = 0.0
    previous_error: float | None = None
    previous_output: float = 0.0
    saturated: bool = False
    integral_limit: float | None = None

    def step(self, error: float, dt: float) -> float:
        if dt <= 0:
            raise ValueError('dt must be positive')
        derivative = 0.0 if self.previous_error is None else (error - self.previous_error) / dt
        candidate = self.integral + error * dt
        if self.integral_limit is not None:
            candidate = max(-self.integral_limit, min(self.integral_limit, candidate))
        raw = self.kp * error + self.ki * candidate + self.kd * derivative
        output = min(self.maximum, max(self.minimum, raw))
        pushing_up = output >= self.maximum - 1e-12 and error > 0
        pushing_down = output <= self.minimum + 1e-12 and error < 0
        if not (pushing_up or pushing_down):
            self.integral = candidate
        self.saturated = output != raw
        self.previous_error = error
        self.previous_output = output
        return output

    def reset(self) -> None:
        self.integral = 0.0
        self.previous_error = None
        self.previous_output = 0.0
        self.saturated = False


@dataclass(frozen=True)
class ActuatorLimits:
    minimum: float
    maximum: float
    max_delta_per_second: float

    def clamp(self, value: float) -> float:
        return min(self.maximum, max(self.minimum, value))


def limit_command(previous: float, desired: float, dt: float, limits: ActuatorLimits) -> float:
    """Slew rate is per second: halving the loop period must not halve the motion."""
    if dt <= 0:
        raise ValueError('dt must be positive')
    target = limits.clamp(desired)
    allowed = limits.max_delta_per_second * dt
    return min(previous + allowed, max(previous - allowed, target))


def limit_pair(previous: Sequence[float], desired: Sequence[float], dt: float,
               limits: Sequence[ActuatorLimits]) -> tuple[float, ...]:
    return tuple(limit_command(p, d, dt, l) for p, d, l in zip(previous, desired, limits))


@dataclass
class GainSchedule:
    """Linear interpolation of gains between speed breakpoints."""

    breakpoints: list[tuple[float, tuple[float, float, float]]] = field(default_factory=list)

    def add(self, speed: float, gains: Iterable[float]) -> 'GainSchedule':
        values = tuple(float(v) for v in gains)
        if len(values) != 3:
            raise ValueError('expected (kp, ki, kd)')
        self.breakpoints.append((float(speed), values))  # type: ignore[arg-type]
        self.breakpoints.sort(key=lambda item: item[0])
        return self

    def gains_at(self, speed: float) -> tuple[float, float, float]:
        if not self.breakpoints:
            raise ValueError('no breakpoints configured')
        if speed <= self.breakpoints[0][0]:
            return self.breakpoints[0][1]
        if speed >= self.breakpoints[-1][0]:
            return self.breakpoints[-1][1]
        for (s0, g0), (s1, g1) in zip(self.breakpoints, self.breakpoints[1:]):
            if s0 <= speed <= s1:
                f = 0.0 if s1 == s0 else (speed - s0) / (s1 - s0)
                return (g0[0] + f * (g1[0] - g0[0]),
                        g0[1] + f * (g1[1] - g0[1]),
                        g0[2] + f * (g1[2] - g0[2]))
        return self.breakpoints[-1][1]


def lateral_error(pose: Pose2, target: tuple[float, float]) -> float:
    """Signed lateral offset of ``target`` in the robot frame (positive to the left)."""
    dx, dy = target[0] - pose.x, target[1] - pose.y
    return -math.sin(pose.yaw) * dx + math.cos(pose.yaw) * dy


def pure_pursuit_curvature(pose: Pose2, target: tuple[float, float], lookahead: float) -> float:
    if lookahead <= 0:
        raise ValueError('lookahead must be positive')
    return 2.0 * lateral_error(pose, target) / (lookahead * lookahead)
