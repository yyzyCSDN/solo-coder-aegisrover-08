"""Durable event log ordered by monotonic time.

Operations need to replay exactly what the robot did, even after an NTP step moved
the wall clock backwards. Events are keyed by a monotonically increasing sequence
and stored through the versioned repository; :meth:`EventStore.snapshot` produces a
digest-protected snapshot so a replay can be checked for equivalence.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator

from .repository import Repository, canonical_json

__all__ = ('StoredEvent', 'EventStore', 'EventGap')

NAMESPACE = 'events'


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    mono_ns: int
    wall_ns: int
    kind: str
    payload: dict

    def to_dict(self) -> dict:
        return {'seq': self.seq, 'mono_ns': self.mono_ns, 'wall_ns': self.wall_ns,
                'kind': self.kind, 'payload': self.payload}

    @staticmethod
    def from_dict(payload: dict) -> 'StoredEvent':
        return StoredEvent(int(payload['seq']), int(payload['mono_ns']), int(payload['wall_ns']),
                           payload['kind'], dict(payload['payload']))


@dataclass(frozen=True)
class EventGap:
    after: int
    missing: tuple[int, ...]


class EventStore:
    def __init__(self, repository: Repository, clock=time.time):
        self._repo = repository
        self._clock = clock
        self._last_mono: int | None = None
        tail = self.tail()
        if tail is not None:
            self._last_mono = tail.mono_ns

    # -- writes ----------------------------------------------------------------
    def append(self, kind: str, payload: dict | None = None, *, mono_ns: int | None = None,
               wall_ns: int | None = None) -> StoredEvent:
        if not kind:
            raise ValueError('kind is required')
        mono = int(mono_ns if mono_ns is not None else time.monotonic_ns())
        if self._last_mono is not None and mono < self._last_mono:
            raise ValueError('monotonic timestamp moved backwards')
        wall = int(wall_ns if wall_ns is not None else self._clock() * 1e9)
        seq = 1 if self.tail() is None else self.tail().seq + 1
        event = StoredEvent(seq, mono, wall, kind, dict(payload or {}))
        self._repo.put(NAMESPACE, f'{seq:012d}', event.to_dict())
        self._last_mono = mono
        return event

    # -- reads -----------------------------------------------------------------
    def tail(self) -> StoredEvent | None:
        key = self._repo.last_key(NAMESPACE)
        return None if key is None else StoredEvent.from_dict(self._repo.get(NAMESPACE, key).payload)

    def events(self) -> Iterator[StoredEvent]:
        for record in self._repo.scan(NAMESPACE):
            yield StoredEvent.from_dict(record.payload)

    def since(self, seq: int) -> list[StoredEvent]:
        return [e for e in self.events() if e.seq > seq]

    def window(self, start_seq: int, end_seq: int) -> list[StoredEvent]:
        return [e for e in self.events() if start_seq <= e.seq <= end_seq]

    def gaps(self) -> list[EventGap]:
        sequences = [e.seq for e in self.events()]
        out: list[EventGap] = []
        for previous, current in zip(sequences, sequences[1:]):
            if current != previous + 1:
                out.append(EventGap(previous, tuple(range(previous + 1, current))))
        return out

    def detect_wall_rollback(self) -> list[int]:
        """Sequence numbers whose wall clock went backwards (display-only field)."""
        out, previous = [], None
        for event in self.events():
            if previous is not None and event.wall_ns < previous:
                out.append(event.seq)
            previous = event.wall_ns
        return out

    # -- snapshot / replay -----------------------------------------------------
    def snapshot(self, state: dict, *, seq: int | None = None) -> dict:
        moment = self.tail().seq if seq is None else seq
        body = canonical_json({'sequence': moment, 'state': state})
        import hashlib

        return {'sequence': moment, 'state': state,
                'digest': hashlib.sha256(body.encode()).hexdigest()}

    def restore(self, snapshot: dict) -> dict:
        body = canonical_json({'sequence': snapshot['sequence'], 'state': snapshot['state']})
        import hashlib

        if hashlib.sha256(body.encode()).hexdigest() != snapshot['digest']:
            raise ValueError('snapshot digest mismatch')
        return snapshot['state']

    def replay(self, snapshot: dict, apply: Callable[[dict, StoredEvent], dict]) -> dict:
        state = self.restore(snapshot)
        for event in self.since(snapshot['sequence']):
            state = apply(state, event)
        return state
