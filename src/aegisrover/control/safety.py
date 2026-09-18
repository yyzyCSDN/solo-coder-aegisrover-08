"""Safety supervision: latched emergency stop generations and speed envelopes.

The emergency stop is *latched and generational*: when a second condition trips while
the robot is already stopped, the latch advances to a new generation, so the reset
token an operator obtained for the first event can no longer clear the second one.
Speed supervision caps the commanded speed by the stopping distance implied by the
current clearance, and records every intervention so the run can be explained later.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Iterable

__all__ = ('Intervention', 'EmergencyStopLatch', 'SafetyZone', 'SafetySupervisor',
           'stopping_distance', 'max_safe_speed')


@dataclass(frozen=True)
class Intervention:
    at: float
    kind: str
    detail: str
    requested: float
    applied: float

    def to_dict(self) -> dict:
        return {'at': self.at, 'kind': self.kind, 'detail': self.detail,
                'requested': round(self.requested, 6), 'applied': round(self.applied, 6)}


@dataclass(frozen=True)
class EmergencyStopLatch:
    latched: bool = False
    generation: int = 0
    reason: str | None = None
    history: tuple[dict, ...] = ()

    def trigger(self, reason: str, *, at: float = 0.0) -> 'EmergencyStopLatch':
        entry = {'at': at, 'event': 'trigger', 'reason': reason, 'generation': self.generation + 1}
        return EmergencyStopLatch(True, self.generation + 1, reason, self.history + (entry,))

    def reset(self, token_generation: int, conditions_clear: bool, *, at: float = 0.0) -> 'EmergencyStopLatch':
        """Only the token matching the *current* generation may clear the latch."""
        if conditions_clear and token_generation == self.generation:
            entry = {'at': at, 'event': 'reset', 'reason': self.reason, 'generation': self.generation}
            return EmergencyStopLatch(False, self.generation, None, self.history + (entry,))
        return self

    def permit_motion(self) -> bool:
        return not self.latched

    def to_dict(self) -> dict:
        return {'latched': self.latched, 'generation': self.generation, 'reason': self.reason,
                'history': [dict(h) for h in self.history]}


def stopping_distance(speed: float, deceleration: float, *, reaction_time: float = 0.0) -> float:
    if deceleration <= 0:
        return math.inf
    speed = abs(speed)
    return speed * reaction_time + speed * speed / (2.0 * deceleration)


def max_safe_speed(clearance: float, deceleration: float, *, reaction_time: float = 0.0) -> float:
    if clearance <= 0 or deceleration <= 0:
        return 0.0
    if reaction_time <= 0:
        return math.sqrt(2.0 * deceleration * clearance)
    a = 1.0 / (2.0 * deceleration)
    b = reaction_time
    c = -clearance
    discriminant = b * b - 4 * a * c
    return (-b + math.sqrt(max(0.0, discriminant))) / (2 * a)


@dataclass(frozen=True)
class SafetyZone:
    name: str
    clearance: float
    max_speed: float | None = None
    deceleration: float = 1.0

    def allowed_speed(self, *, reaction_time: float = 0.0) -> float:
        envelope = max_safe_speed(self.clearance, self.deceleration, reaction_time=reaction_time)
        if self.max_speed is None:
            return envelope
        return min(self.max_speed, envelope)


@dataclass
class SafetySupervisor:
    deceleration: float = 1.0
    reaction_time: float = 0.0
    emergency: EmergencyStopLatch = field(default_factory=EmergencyStopLatch)
    interventions: list[Intervention] = field(default_factory=list)
    clock: object = time.time

    def trigger_emergency(self, reason: str) -> EmergencyStopLatch:
        self.emergency = self.emergency.trigger(reason, at=self._now())
        self._record('emergency_stop', reason, 0.0, 0.0)
        return self.emergency

    def reset_emergency(self, token_generation: int, conditions_clear: bool) -> EmergencyStopLatch:
        before = self.emergency.generation
        self.emergency = self.emergency.reset(token_generation, conditions_clear, at=self._now())
        if self.emergency.generation == before and not self.emergency.latched:
            self._record('emergency_reset', f'generation {token_generation}', 0.0, 0.0)
        return self.emergency

    def command(self, requested_speed: float, *, clearance: float | None = None,
                zone: SafetyZone | None = None) -> float:
        if self.emergency.latched:
            self._record('emergency_block', self.emergency.reason or '', requested_speed, 0.0)
            return 0.0
        limit = math.inf
        detail = ''
        if zone is not None:
            limit = min(limit, zone.allowed_speed(reaction_time=self.reaction_time))
            detail = f'zone {zone.name}'
        if clearance is not None:
            limit = min(limit, max_safe_speed(clearance, self.deceleration,
                                              reaction_time=self.reaction_time))
            detail = detail or f'clearance {clearance:.3f}'
        applied = min(abs(requested_speed), limit) * (1.0 if requested_speed >= 0 else -1.0)
        if abs(applied) < abs(requested_speed) - 1e-9:
            self._record('speed_cap', detail, requested_speed, applied)
        return applied

    def enforce_minimum_clearance(self, zones: Iterable[SafetyZone], speed: float) -> float:
        allowed = min(zone.allowed_speed(reaction_time=self.reaction_time) for zone in zones)
        if abs(speed) > allowed + 1e-9:
            self._record('zone_cap', 'min clearance', speed, allowed)
            return math.copysign(allowed, speed)
        return speed

    def to_dict(self) -> dict:
        return {'emergency': self.emergency.to_dict(),
                'interventions': [i.to_dict() for i in self.interventions]}

    def _record(self, kind: str, detail: str, requested: float, applied: float) -> None:
        self.interventions.append(Intervention(self._now(), kind, detail, requested, applied))

    def _now(self) -> float:
        return float(self.clock())  # type: ignore[operator]
