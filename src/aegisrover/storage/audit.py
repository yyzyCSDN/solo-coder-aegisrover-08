"""Append-only audit trail with a hash chain.

Operators need to prove that the recorded sequence of operator actions and
automatic transitions was not edited after the fact. Each entry stores the digest
of the previous entry, so any change to an historical row invalidates every later
digest and :meth:`AuditLog.verify` reports the first broken sequence number.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Iterable, Iterator

from .repository import Repository, canonical_json
import hashlib

__all__ = ('AuditEntry', 'AuditLog', 'AuditBreak')

GENESIS = '0' * 64
NAMESPACE = 'audit'


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    recorded_at: float
    actor: str
    action: str
    subject: str
    payload: dict
    previous_digest: str
    digest: str

    def material(self) -> str:
        return '\x1f'.join((
            str(self.seq),
            f'{self.recorded_at:.6f}',
            self.actor,
            self.action,
            self.subject,
            canonical_json(self.payload),
            self.previous_digest,
        ))


@dataclass(frozen=True)
class AuditBreak:
    seq: int
    reason: str


class AuditLog:
    """Hash-chained audit log persisted through :class:`Repository`."""

    def __init__(self, repository: Repository, clock=time.time):
        self._repo = repository
        self._clock = clock

    # -- writing ---------------------------------------------------------------
    def append(self, actor: str, action: str, subject: str, payload: Any = None) -> AuditEntry:
        if not actor or not action or not subject:
            raise ValueError('actor, action and subject are required')
        head = self.head()
        seq = 1 if head is None else head.seq + 1
        recorded_at = self._clock()
        entry = AuditEntry(
            seq=seq,
            recorded_at=recorded_at,
            actor=actor,
            action=action,
            subject=subject,
            payload=dict(payload or {}),
            previous_digest=GENESIS if head is None else head.digest,
            digest='',
        )
        digest = hashlib.sha256(entry.material().encode()).hexdigest()
        entry = replace(entry, digest=digest)
        self._repo.put(NAMESPACE, f'{seq:012d}', {
            'seq': entry.seq,
            'recorded_at': entry.recorded_at,
            'actor': entry.actor,
            'action': entry.action,
            'subject': entry.subject,
            'payload': entry.payload,
            'previous_digest': entry.previous_digest,
            'digest': entry.digest,
        })
        return entry

    # -- reading ---------------------------------------------------------------
    def head(self) -> AuditEntry | None:
        last = self._repo.last_key(NAMESPACE)
        if last is None:
            return None
        return self._entry(self._repo.get(NAMESPACE, last).payload)

    def entries(self) -> Iterator[AuditEntry]:
        for record in self._repo.scan(NAMESPACE):
            yield self._entry(record.payload)

    def verify(self) -> tuple[AuditBreak, ...]:
        """Return every place where the chain is broken (empty means intact)."""
        breaks: list[AuditBreak] = []
        previous = GENESIS
        expected_seq = 1
        for entry in self.entries():
            if entry.seq != expected_seq:
                breaks.append(AuditBreak(entry.seq, f'expected sequence {expected_seq}'))
            if entry.previous_digest != previous:
                breaks.append(AuditBreak(entry.seq, 'previous digest mismatch'))
            recomputed = hashlib.sha256(entry.material().encode()).hexdigest()
            if recomputed != entry.digest:
                breaks.append(AuditBreak(entry.seq, 'entry digest mismatch'))
            previous = entry.digest
            expected_seq = entry.seq + 1
        return tuple(breaks)

    def export(self) -> list[dict]:
        return [e.__dict__ for e in self.entries()]

    def tamper(self, seq: int, **changes) -> None:
        """Test helper: rewrite a stored entry without fixing the chain."""
        key = f'{seq:012d}'
        record = self._repo.get(NAMESPACE, key)
        payload = dict(record.payload)
        payload.update(changes)
        self._repo.put(NAMESPACE, key, payload, expected=record.version)

    @staticmethod
    def _entry(payload: dict) -> AuditEntry:
        return AuditEntry(
            seq=int(payload['seq']),
            recorded_at=float(payload['recorded_at']),
            actor=payload['actor'],
            action=payload['action'],
            subject=payload['subject'],
            payload=dict(payload.get('payload') or {}),
            previous_digest=payload['previous_digest'],
            digest=payload['digest'],
        )
