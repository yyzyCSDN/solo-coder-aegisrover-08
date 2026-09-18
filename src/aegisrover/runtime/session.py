"""Operator sessions with leases and independent CPU / wall-clock budgets.

A session represents one operator (or one automation client) driving a robot for a
bounded amount of time. Two budget dimensions are tracked separately on purpose:
a job that blocks on external input burns almost no CPU but can still hold a robot
forever, so the wall-clock budget has to be able to fire on its own.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Iterable, Iterator

from aegisrover.storage.audit import AuditLog
from aegisrover.storage.repository import Repository

__all__ = ('Session', 'Budget', 'SessionError', 'SessionRegistry')

SESSION_NAMESPACE = 'sessions'
ACTIVE = 'active'
EXPIRED = 'expired'
CLOSED = 'closed'


class SessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Budget:
    """CPU seconds and wall seconds are independent limits."""

    cpu_limit: float
    wall_limit: float
    cpu_used: float = 0.0
    started_wall: float = 0.0

    def charge_cpu(self, delta: float) -> 'Budget':
        if delta < 0:
            raise SessionError('cpu charge must not be negative')
        return replace(self, cpu_used=self.cpu_used + delta)

    def evaluate(self, now_wall: float) -> dict:
        wall_used = max(0.0, now_wall - self.started_wall)
        exceeded = []
        if self.cpu_used > self.cpu_limit:
            exceeded.append('cpu')
        if wall_used > self.wall_limit:
            exceeded.append('wall')
        return {
            'cpu_used': round(self.cpu_used, 6),
            'wall_used': round(wall_used, 6),
            'cpu_remaining': round(max(0.0, self.cpu_limit - self.cpu_used), 6),
            'wall_remaining': round(max(0.0, self.wall_limit - wall_used), 6),
            'exceeded': exceeded,
            'status': 'timeout' if exceeded else 'ok',
        }


@dataclass(frozen=True)
class Session:
    session_id: str
    robot: str
    operator: str
    opened_at: float
    lease_expires_at: float
    heartbeat_at: float
    state: str
    budget: Budget
    capabilities: frozenset[str] = frozenset()
    audit_trail: tuple[dict, ...] = ()
    revision: int = 1

    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'robot': self.robot,
            'operator': self.operator,
            'opened_at': self.opened_at,
            'lease_expires_at': self.lease_expires_at,
            'heartbeat_at': self.heartbeat_at,
            'state': self.state,
            'budget': {'cpu_limit': self.budget.cpu_limit, 'wall_limit': self.budget.wall_limit,
                       'cpu_used': self.budget.cpu_used, 'started_wall': self.budget.started_wall},
            'capabilities': sorted(self.capabilities),
            'audit_trail': [dict(item) for item in self.audit_trail],
            'revision': self.revision,
        }

    @staticmethod
    def from_dict(payload: dict) -> 'Session':
        budget = payload['budget']
        return Session(
            session_id=payload['session_id'],
            robot=payload['robot'],
            operator=payload['operator'],
            opened_at=float(payload['opened_at']),
            lease_expires_at=float(payload['lease_expires_at']),
            heartbeat_at=float(payload['heartbeat_at']),
            state=payload['state'],
            budget=Budget(float(budget['cpu_limit']), float(budget['wall_limit']),
                          float(budget['cpu_used']), float(budget['started_wall'])),
            capabilities=frozenset(payload.get('capabilities') or ()),
            audit_trail=tuple(payload.get('audit_trail') or ()),
            revision=int(payload.get('revision', 1)),
        )


class SessionRegistry:
    """Durable session table.

    A session holds a lease that must be renewed by :meth:`heartbeat`. When the
    lease lapses the registry marks the session ``expired`` instead of deleting it,
    so the run record keeps explaining who held the robot at that time.
    """

    def __init__(self, repository: Repository, audit: AuditLog | None = None, clock=time.time,
                 id_factory=None):
        self._repo = repository
        self._audit = audit if audit is not None else AuditLog(repository, clock)
        self._clock = clock
        self._new_id = id_factory or (lambda: uuid.uuid4().hex[:12])

    # -- lifecycle -------------------------------------------------------------
    def open(self, robot: str, operator: str, *, lease_seconds: float = 30.0,
             cpu_limit: float = 600.0, wall_limit: float = 1800.0,
             capabilities: Iterable[str] = (), actor: str | None = None) -> Session:
        if lease_seconds <= 0 or cpu_limit <= 0 or wall_limit <= 0:
            raise SessionError('lease, cpu and wall limits must be positive')
        now = self._clock()
        for existing in self.list_sessions(state=ACTIVE):
            if existing.robot == robot:
                if now < existing.lease_expires_at:
                    raise SessionError(f'{robot} already leased by {existing.operator}')
                self._mark(existing, EXPIRED, actor or 'registry', 'lease lapsed')
        session = Session(
            session_id=self._new_id(),
            robot=robot,
            operator=operator,
            opened_at=now,
            lease_expires_at=now + lease_seconds,
            heartbeat_at=now,
            state=ACTIVE,
            budget=Budget(cpu_limit=cpu_limit, wall_limit=wall_limit, started_wall=now),
            capabilities=frozenset(capabilities),
            audit_trail=({'at': now, 'event': 'open', 'actor': operator},),
        )
        self._repo.put(SESSION_NAMESPACE, session.session_id, session.to_dict())
        self._audit.append(operator, 'session.open', session.session_id,
                           {'robot': robot, 'lease_seconds': lease_seconds,
                            'cpu_limit': cpu_limit, 'wall_limit': wall_limit})
        return session

    def heartbeat(self, session_id: str, *, lease_seconds: float | None = None,
                  cpu_delta: float = 0.0, actor: str | None = None) -> Session:
        session = self.get(session_id)
        if session.state != ACTIVE:
            raise SessionError(f'session {session_id} is {session.state}')
        now = self._clock()
        window = lease_seconds if lease_seconds is not None else session.lease_expires_at - session.heartbeat_at
        budget = session.budget.charge_cpu(cpu_delta)
        status = budget.evaluate(now)
        trail = session.audit_trail + ({'at': now, 'event': 'heartbeat', 'actor': actor or session.operator,
                                        'cpu_delta': cpu_delta},)
        updated = replace(
            session,
            heartbeat_at=now,
            lease_expires_at=now + window,
            budget=budget,
            audit_trail=trail,
            revision=session.revision + 1,
        )
        self._repo.put(SESSION_NAMESPACE, session_id, updated.to_dict(),
                       expected=self._repo.get(SESSION_NAMESPACE, session_id).version)
        if status['status'] == 'timeout':
            return self._mark(updated, EXPIRED, actor or 'watchdog',
                              'budget exceeded: ' + ','.join(status['exceeded']))
        return updated

    def close(self, session_id: str, *, actor: str | None = None, reason: str = '') -> Session:
        return self._mark(self.get(session_id), CLOSED, actor or 'operator', reason)

    def expire(self, now: float | None = None, *, actor: str = 'registry') -> list[Session]:
        moment = self._clock() if now is None else now
        expired = []
        for session in self.list_sessions(state=ACTIVE):
            if moment >= session.lease_expires_at:
                expired.append(self._mark(session, EXPIRED, actor, 'lease lapsed'))
                continue
            status = session.budget.evaluate(moment)
            if status['status'] == 'timeout':
                expired.append(self._mark(session, EXPIRED, actor,
                                          'budget exceeded: ' + ','.join(status['exceeded'])))
        return expired

    # -- reads -----------------------------------------------------------------
    def get(self, session_id: str) -> Session:
        return Session.from_dict(self._repo.get(SESSION_NAMESPACE, session_id).payload)

    def list_sessions(self, *, state: str | None = None) -> list[Session]:
        items = [Session.from_dict(r.payload) for r in self._repo.scan(SESSION_NAMESPACE)]
        if state is not None:
            items = [s for s in items if s.state == state]
        return sorted(items, key=lambda s: s.opened_at)

    def lease_holder(self, robot: str) -> Session | None:
        for session in self.list_sessions(state=ACTIVE):
            if session.robot == robot:
                return session
        return None

    def utilisation(self, robot: str) -> float:
        sessions = [s for s in self.list_sessions() if s.robot == robot]
        if not sessions:
            return 0.0
        busy = sum(max(0.0, s.lease_expires_at - s.opened_at) for s in sessions)
        span = max(s.lease_expires_at for s in sessions) - min(s.opened_at for s in sessions)
        return 0.0 if span <= 0 else min(1.0, busy / span)

    # -- internals -------------------------------------------------------------
    def _mark(self, session: Session, state: str, actor: str, reason: str) -> Session:
        now = self._clock()
        trail = session.audit_trail + ({'at': now, 'event': state, 'actor': actor, 'reason': reason},)
        updated = replace(session, state=state, audit_trail=trail, revision=session.revision + 1,
                          heartbeat_at=now)
        record = self._repo.get(SESSION_NAMESPACE, session.session_id)
        self._repo.put(SESSION_NAMESPACE, session.session_id, updated.to_dict(), expected=record.version)
        self._audit.append(actor, f'session.{state}', session.session_id,
                           {'robot': session.robot, 'reason': reason})
        return updated
