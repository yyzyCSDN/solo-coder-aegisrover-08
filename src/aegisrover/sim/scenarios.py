"""Scenario library: versioned scenarios with reproducible replay.

Scenarios are stored as immutable revisions in the versioned repository; each
revision carries a digest of its normalised payload. Replaying a revision twice must
produce the same run digest, and that check is part of the library's contract rather
than something an operator has to eyeball.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, replace
from typing import Iterable

from aegisrover.storage.audit import AuditLog
from aegisrover.storage.repository import Repository, canonical_json
from aegisrover.sim.engine import RunResult, SimulationEngine

__all__ = ('ScenarioSpec', 'ScenarioStore', 'ScenarioError')

NAMESPACE = 'scenarios'


class ScenarioError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    revision: int
    duration: float
    step: float = 0.1
    seed: int = 0
    robots: tuple[dict, ...] = ()
    events: tuple[dict, ...] = ()
    notes: str = ''
    digest: str = ''

    def normalised(self) -> dict:
        return {
            'scenario_id': self.scenario_id,
            'revision': self.revision,
            'duration': round(self.duration, 9),
            'step': round(self.step, 9),
            'seed': self.seed,
            'robots': [dict(r) for r in self.robots],
            'events': [{'time': round(e['time'], 9), 'kind': e['kind'],
                        'payload': dict(e.get('payload') or {})} for e in self.events],
            'notes': self.notes,
        }

    def to_dict(self) -> dict:
        payload = self.normalised()
        payload['digest'] = self.digest
        return payload

    @staticmethod
    def from_dict(payload: dict) -> 'ScenarioSpec':
        return ScenarioSpec(
            scenario_id=payload['scenario_id'],
            revision=int(payload['revision']),
            duration=float(payload['duration']),
            step=float(payload.get('step', 0.1)),
            seed=int(payload.get('seed', 0)),
            robots=tuple(dict(r) for r in payload.get('robots') or ()),
            events=tuple({'time': float(e['time']), 'kind': e['kind'],
                          'payload': dict(e.get('payload') or {})} for e in payload.get('events') or ()),
            notes=payload.get('notes', ''),
            digest=payload.get('digest', ''),
        )


def compute_digest(payload: dict) -> str:
    body = canonical_json({k: v for k, v in payload.items() if k != 'digest'})
    return hashlib.sha256(body.encode()).hexdigest()


class ScenarioStore:
    def __init__(self, repository: Repository, audit: AuditLog | None = None, clock=time.time):
        self._repo = repository
        self._audit = audit if audit is not None else AuditLog(repository, clock)
        self._clock = clock

    # -- writes ----------------------------------------------------------------
    def save(self, spec: ScenarioSpec, *, actor: str = 'planner') -> ScenarioSpec:
        if spec.duration <= 0:
            raise ScenarioError('duration must be positive')
        if spec.step <= 0:
            raise ScenarioError('step must be positive')
        ordered = tuple(sorted(spec.events, key=lambda e: e['time']))
        for previous, current in zip(ordered, ordered[1:]):
            if current['time'] < previous['time']:
                raise ScenarioError('events must be time ordered')
        latest = self.latest(spec.scenario_id)
        revision = 1 if latest is None else latest.revision + 1
        staged = replace(spec, revision=revision, events=ordered)
        digest = compute_digest(staged.normalised())
        record = replace(staged, digest=digest)
        self._repo.put(NAMESPACE, f'{spec.scenario_id}@{revision:04d}', record.to_dict())
        self._audit.append(actor, 'scenario.save', spec.scenario_id,
                           {'revision': revision, 'digest': digest, 'events': len(ordered)})
        return record

    # -- reads -----------------------------------------------------------------
    def get(self, scenario_id: str, revision: int | None = None) -> ScenarioSpec:
        target = self.latest(scenario_id) if revision is None else self._read(scenario_id, revision)
        if target is None:
            raise ScenarioError(f'unknown scenario {scenario_id!r}')
        return target

    def latest(self, scenario_id: str) -> ScenarioSpec | None:
        key = self._repo.last_key(NAMESPACE)
        if key is None:
            return None
        candidates = [ScenarioSpec.from_dict(r.payload) for r in self._repo.scan(NAMESPACE)
                      if r.key.startswith(f'{scenario_id}@')]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.revision)

    def revisions(self, scenario_id: str) -> list[ScenarioSpec]:
        items = [ScenarioSpec.from_dict(r.payload) for r in self._repo.scan(NAMESPACE)
                 if r.key.startswith(f'{scenario_id}@')]
        return sorted(items, key=lambda s: s.revision)

    def verify(self, spec: ScenarioSpec) -> bool:
        return spec.digest == compute_digest(spec.normalised())

    def diff(self, left: ScenarioSpec, right: ScenarioSpec) -> dict:
        a, b = left.normalised(), right.normalised()
        keys = set(a) | set(b)
        changed = {k: {'left': a.get(k), 'right': b.get(k)} for k in sorted(keys) if a.get(k) != b.get(k)}
        return {'scenario_id': left.scenario_id, 'from_revision': left.revision,
                'to_revision': right.revision, 'changed_fields': changed}

    # -- replay ----------------------------------------------------------------
    def build_engine(self, spec: ScenarioSpec) -> SimulationEngine:
        engine = SimulationEngine(step=spec.step, seed=spec.seed)
        for robot in spec.robots:
            from aegisrover.core.types import Pose2, Twist2

            pose = robot.get('pose') or [0.0, 0.0, 0.0]
            twist = robot.get('twist') or [0.0, 0.0]
            engine.add_robot(robot['name'], Pose2(*[float(v) for v in pose]), Twist2(*[float(v) for v in twist]))
        engine.schedule_from_spec([
            {'time': e['time'], 'kind': e['kind'], 'payload': e['payload']} for e in spec.events
        ])
        return engine

    def replay(self, spec: ScenarioSpec) -> RunResult:
        if not self.verify(spec):
            raise ScenarioError(f'scenario {spec.scenario_id}@{spec.revision} digest mismatch')
        engine = self.build_engine(spec)
        return engine.run(spec.duration, on_event=_apply_event)

    def replay_twice(self, spec: ScenarioSpec) -> tuple[RunResult, RunResult, bool]:
        first = self.replay(spec)
        second = self.replay(spec)
        return first, second, first.digest == second.digest

    def require_reproducible(self, spec: ScenarioSpec) -> RunResult:
        first, second, same = self.replay_twice(spec)
        if not same:
            raise ScenarioError(f'scenario {spec.scenario_id} is not reproducible')
        return first

    def _read(self, scenario_id: str, revision: int) -> ScenarioSpec | None:
        record = self._repo.maybe_get(NAMESPACE, f'{scenario_id}@{revision:04d}')
        return None if record is None else ScenarioSpec.from_dict(record.payload)


def _apply_event(event, engine) -> None:
    """Built-in event vocabulary used by scenario files."""
    payload = event.payload
    if event.kind == 'set_twist':
        from aegisrover.core.types import Twist2

        robot = engine.world.robots[payload['robot']]
        robot.twist = Twist2(float(payload.get('linear', 0.0)), float(payload.get('angular', 0.0)))
    elif event.kind == 'stop':
        from aegisrover.core.types import Twist2

        for name in payload.get('robots', list(engine.world.robots)):
            engine.world.robots[name].twist = Twist2(0.0, 0.0)
    elif event.kind == 'teleport':
        from aegisrover.core.types import Pose2

        robot = engine.world.robots[payload['robot']]
        x, y, yaw = payload['pose']
        robot.pose = Pose2(float(x), float(y), float(yaw))
    else:
        raise ScenarioError(f'unknown event kind {event.kind!r}')
