"""Deterministic simulation engine: fixed steps, injected events, reproducible digests.

Two rules make a run reproducible. First, the world always advances in fixed steps,
so an event scheduled at t=1.05 in a 0.1 s simulation fires on the same step no
matter how fast the host is. Second, events that share a timestamp are applied in
registration order — the tie-break is part of the trace digest, so changing it shows
up as a different run instead of silently reordering results.
"""
from __future__ import annotations

import hashlib
import itertools
import random
from dataclasses import dataclass, field
from typing import Callable, Iterable

from aegisrover.core.types import Pose2, Twist2
from aegisrover.sim.world import Robot, World
from aegisrover.storage.repository import canonical_json

__all__ = ('Event', 'RunResult', 'SimulationEngine', 'SimulationError')


class SimulationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Event:
    time: float
    kind: str
    payload: dict = field(default_factory=dict)
    sequence: int = 0

    @property
    def order_key(self) -> tuple[float, int]:
        return (self.time, self.sequence)

    def to_dict(self) -> dict:
        return {'time': self.time, 'kind': self.kind, 'payload': self.payload, 'sequence': self.sequence}


@dataclass(frozen=True)
class RunResult:
    duration: float
    steps: int
    trace: tuple[dict, ...]
    events_applied: tuple[Event, ...]
    digest: str
    seed: int

    def final_pose(self, robot: str) -> dict:
        for sample in reversed(self.trace):
            if robot in sample['robots']:
                return sample['robots'][robot]
        raise SimulationError(f'robot {robot!r} never sampled')


class SimulationEngine:
    """Fixed-step engine with deterministic event ordering."""

    def __init__(self, *, step: float = 0.1, seed: int = 0,
                 noise: Callable[[random.Random, float], Twist2] | None = None):
        if step <= 0:
            raise SimulationError('step must be positive')
        self.step = step
        self.seed = seed
        self.noise = noise
        self.world = World()
        self.time = 0.0
        self._events: list[Event] = []
        self._counter = itertools.count(1)

    # -- setup -----------------------------------------------------------------
    def add_robot(self, name: str, pose: Pose2 | None = None, twist: Twist2 | None = None) -> Robot:
        robot = Robot(name, pose or Pose2(0.0, 0.0, 0.0), twist or Twist2(0.0, 0.0))
        self.world.add(robot)
        return robot

    def schedule(self, time: float, kind: str, payload: dict | None = None) -> Event:
        if time < self.time:
            raise SimulationError('cannot schedule an event in the past')
        event = Event(float(time), kind, dict(payload or {}), next(self._counter))
        self._events.append(event)
        self._events.sort(key=lambda e: e.order_key)
        return event

    def schedule_from_spec(self, events: Iterable[dict]) -> list[Event]:
        out = []
        for item in events:
            out.append(self.schedule(item['time'], item['kind'], item.get('payload')))
        return out

    # -- execution -------------------------------------------------------------
    def run(self, duration: float, *, on_event: Callable[[Event, SimulationEngine], None] | None = None) -> RunResult:
        if duration <= 0:
            raise SimulationError('duration must be positive')
        rng = random.Random(self.seed)
        trace: list[dict] = []
        applied: list[Event] = []
        remaining = duration
        while remaining > 1e-12:
            target = self.time + self.step
            while self._events and self._events[0].time <= target + 1e-12:
                event = self._events.pop(0)
                self.time = event.time
                if on_event is not None:
                    on_event(event, self)
                applied.append(event)
            self.time = target
            if self.noise is not None:
                for robot in self.world.robots.values():
                    delta = self.noise(rng, self.step)
                    robot.twist = Twist2(robot.twist.linear + delta.linear,
                                         robot.twist.angular + delta.angular)
            poses = self.world.step(self.step)
            trace.append({'time': round(self.time, 9), 'robots': {n: _pose_dict(p) for n, p in poses.items()}})
            remaining -= self.step
        digest = _digest(self.step, self.seed, trace, [e.to_dict() for e in applied])
        return RunResult(duration=self.time, steps=len(trace), trace=tuple(trace),
                         events_applied=tuple(applied), digest=digest, seed=self.seed)

    @staticmethod
    def digest_of(result: RunResult) -> str:
        return result.digest


def _pose_dict(pose: Pose2) -> dict:
    return {'x': round(pose.x, 9), 'y': round(pose.y, 9), 'yaw': round(pose.yaw, 9)}


def _digest(step: float, seed: int, trace: list[dict], events: list[dict]) -> str:
    material = canonical_json({'step': step, 'seed': seed, 'trace': trace, 'events': events})
    return hashlib.sha256(material.encode()).hexdigest()


def constant_twist(robot_name: str, linear: float, angular: float) -> Callable[[Event, SimulationEngine], None]:
    """Helper: an event handler that sets a robot's twist."""

    def apply(_event: Event, engine: SimulationEngine) -> None:
        robot = engine.world.robots[robot_name]
        robot.twist = Twist2(linear, angular)

    return apply
