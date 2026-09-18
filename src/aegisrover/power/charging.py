"""Docking alignment and charging sessions.

Alignment errors are expressed in the *dock's* frame, so a dock that happens to face
90 degrees still reports a small lateral error for a robot that approaches correctly.
A charging session is a small state machine: it cannot charge before contact, it
aborts (and requires re-alignment) if the robot drifts off the pad while current is
flowing, and it records every transition for the run record.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from aegisrover.core.types import Pose2, wrap_angle
from aegisrover.power.energy import BatteryPack

__all__ = ('DockAlignment', 'docking_error', 'is_aligned', 'ChargingSession', 'ChargingError')


class ChargingError(RuntimeError):
    pass


@dataclass(frozen=True)
class DockAlignment:
    longitudinal_tolerance: float = 0.05
    lateral_tolerance: float = 0.05
    heading_tolerance: float = math.radians(5)

    def __post_init__(self):
        if min(self.longitudinal_tolerance, self.lateral_tolerance, self.heading_tolerance) <= 0:
            raise ValueError('tolerances must be positive')


def docking_error(robot: Pose2, dock: Pose2) -> tuple[float, float, float]:
    """Return ``(forward, left, heading_error)`` of the robot in the dock frame.

    ``forward`` is the separation along the dock's approach axis (so a robot that has
    not reached the pad yet has a positive value), ``left`` is the lateral offset, and
    the heading error is wrapped into ``[-pi, pi]``.
    """
    dx, dy = robot.x - dock.x, robot.y - dock.y
    cos_yaw, sin_yaw = math.cos(dock.yaw), math.sin(dock.yaw)
    forward = cos_yaw * dx + sin_yaw * dy
    left = -sin_yaw * dx + cos_yaw * dy
    return (forward, left, wrap_angle(robot.yaw - dock.yaw))


def is_aligned(robot: Pose2, dock: Pose2, alignment: DockAlignment | None = None) -> bool:
    limits = alignment or DockAlignment()
    forward, left, heading = docking_error(robot, dock)
    return (abs(forward) <= limits.longitudinal_tolerance
            and abs(left) <= limits.lateral_tolerance
            and abs(heading) <= limits.heading_tolerance)


@dataclass
class ChargingSession:
    session_id: str
    dock: Pose2
    battery: BatteryPack
    alignment: DockAlignment = field(default_factory=DockAlignment)
    state: str = 'approach'
    events: list[dict] = field(default_factory=list)
    charged_ah: float = 0.0
    target_soc: float = 1.0

    def _log(self, kind: str, payload: dict | None = None) -> None:
        self.events.append({'at': time.time(), 'event': kind, **(payload or {})})

    # -- lifecycle -------------------------------------------------------------
    def observe(self, robot: Pose2) -> str:
        forward, left, heading = docking_error(robot, self.dock)
        aligned = is_aligned(robot, self.dock, self.alignment)
        if self.state == 'approach':
            if forward <= self.alignment.longitudinal_tolerance and aligned:
                self.state = 'contact'
                self._log('contact', {'forward': forward, 'left': left})
            return self.state
        if self.state in ('contact', 'charging'):
            if abs(left) > self.alignment.lateral_tolerance * 3 or abs(heading) > self.alignment.heading_tolerance * 3:
                self.abort(f'robot drifted off the pad (left={left:.3f}, heading={heading:.3f})')
        return self.state

    def start_charge(self, current_a: float) -> str:
        if self.state != 'contact':
            raise ChargingError(f'cannot charge while {self.state}')
        if current_a <= 0:
            raise ChargingError('charging current must be positive')
        self.state = 'charging'
        self._log('charge_start', {'current_a': current_a})
        return self.state

    def step(self, current_a: float, dt_seconds: float) -> float:
        if self.state != 'charging':
            raise ChargingError(f'session is {self.state}')
        before = self.battery.soc
        self.battery.integrate(-abs(current_a), dt_seconds)
        self.charged_ah += (self.battery.soc - before) * self.battery.capacity_ah
        if self.battery.soc >= self.target_soc - 1e-9:
            self.state = 'complete'
            self._log('charge_complete', {'soc': self.battery.soc, 'charged_ah': self.charged_ah})
        return self.battery.soc

    def abort(self, reason: str) -> str:
        if self.state in ('complete', 'aborted'):
            return self.state
        self.state = 'aborted'
        self._log('abort', {'reason': reason})
        return self.state

    def realign(self) -> str:
        if self.state != 'aborted':
            raise ChargingError('only an aborted session can be re-aligned')
        self.state = 'approach'
        self._log('realign')
        return self.state

    def summary(self) -> dict:
        return {'session_id': self.session_id, 'state': self.state,
                'soc': round(self.battery.soc, 6), 'charged_ah': round(self.charged_ah, 6),
                'events': [e['event'] for e in self.events]}
