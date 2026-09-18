"""Hierarchical admission control with bounded queues and overload policies.

Quotas form a tree (fleet -> robot -> client). A request must pass every level before
any token is consumed, so a rejection never leaves a parent quota half-charged. When
the queue is full the configured policy decides whether the newest request is
rejected, the lowest-priority queued item is shed, or the caller is told to retry.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import Iterable

from .rate import TokenBucket
from .ring import Ring

__all__ = ('Quota', 'Admission', 'QueueItem', 'AdmissionController')


@dataclass
class Quota:
    name: str
    rate: float
    burst: float
    parent: 'Quota | None' = None
    bucket: TokenBucket = field(init=False, repr=False)
    children: list['Quota'] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self.bucket = TokenBucket(self.rate, self.burst)
        if self.parent is not None:
            self.parent.children.append(self)

    def chain(self) -> list['Quota']:
        node, out = self, []
        while node is not None:
            out.append(node)
            node = node.parent
        return out


@dataclass(frozen=True)
class Admission:
    allowed: bool
    reason: str = ''
    retry_after: float = 0.0
    charged: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {'allowed': self.allowed, 'reason': self.reason,
                'retry_after': round(self.retry_after, 6), 'charged': list(self.charged)}


@dataclass(order=True)
class QueueItem:
    priority: int
    sequence: int
    key: str = field(compare=False)
    cost: float = field(compare=False, default=1.0)
    quota: str = field(compare=False, default='global')


class AdmissionController:
    def __init__(self, *, queue_limit: int = 32, policy: str = 'reject', recent: int = 32):
        if policy not in ('reject', 'shed_lowest', 'delay'):
            raise ValueError('unknown policy')
        self.queue_limit = queue_limit
        self.policy = policy
        self._quotas: dict[str, Quota] = {}
        self._queue: list[QueueItem] = []
        self._counter = itertools.count()
        self._recent = Ring(recent)
        self.admitted = 0
        self.rejected = 0
        self.shed = 0

    # -- setup -----------------------------------------------------------------
    def add_quota(self, name: str, rate: float, burst: float, parent: str | None = None) -> Quota:
        if name in self._quotas:
            raise ValueError(f'quota {name!r} already registered')
        parent_quota = None if parent is None else self._quotas.get(parent)
        if parent is not None and parent_quota is None:
            raise ValueError(f'unknown parent quota {parent!r}')
        quota = Quota(name, rate, burst, parent_quota)
        self._quotas[name] = quota
        return quota

    def quota(self, name: str) -> Quota:
        try:
            return self._quotas[name]
        except KeyError:
            raise KeyError(f'unknown quota {name!r}') from None

    # -- admission -------------------------------------------------------------
    def admit(self, key: str, *, now: float, cost: float = 1.0, quota: str = 'global',
              priority: int = 0) -> Admission:
        chain = self.quota(quota).chain()
        shortfall = [(q, self._deficit(q, now, cost)) for q in chain]
        blocked = [(q, deficit) for q, deficit in shortfall if deficit > 0]
        if blocked:
            self.rejected += 1
            self._recent.append({'at': now, 'key': key, 'reason': 'quota',
                                 'quota': blocked[0][0].name})
            wait = max(deficit / (q.rate or 1.0) for q, deficit in blocked)
            if self.policy == 'delay':
                return Admission(False, 'delayed', wait, tuple())
            return Admission(False, f'quota:{blocked[0][0].name}', wait, tuple())
        if key in self._queue_keys():
            return Admission(False, 'already_queued', 0.0, tuple())
        for bucket_quota, deficit in shortfall:
            bucket_quota.bucket.allow(now, cost)
        self.admitted += 1
        return Admission(True, '', 0.0, tuple(q.name for q in chain))

    def enqueue(self, key: str, *, now: float, cost: float = 1.0, priority: int = 0,
                quota: str = 'global') -> Admission:
        if len(self._queue) >= self.queue_limit:
            if self.policy == 'shed_lowest':
                # QueueItem.priority is stored negated so heapq pops the highest
                # priority first; the victim is the item with the *lowest* real priority.
                victim = max(self._queue, key=lambda item: (item.priority, -item.sequence))
                if -victim.priority < priority:
                    self._queue.remove(victim)
                    heapq.heapify(self._queue)
                    self.shed += 1
                else:
                    self.rejected += 1
                    self._recent.append({'at': now, 'key': key, 'reason': 'queue_full'})
                    return Admission(False, 'queue_full', 0.0, tuple())
            else:
                self.rejected += 1
                self._recent.append({'at': now, 'key': key, 'reason': 'queue_full'})
                return Admission(False, 'queue_full', 0.0, tuple())
        admitted = self.admit(key, now=now, cost=cost, quota=quota, priority=priority)
        if admitted.allowed:
            heapq.heappush(self._queue, QueueItem(-priority, next(self._counter), key, cost, quota))
        return admitted

    def pop_ready(self, *, now: float, limit: int = 1) -> list[str]:
        """Pop queued keys while quota allows (highest priority first)."""
        out: list[str] = []
        while self._queue and len(out) < limit:
            item = self._queue[0]
            chain = self.quota(item.quota).chain()
            if any(self._deficit(q, now, item.cost) > 0 for q in chain):
                break
            heapq.heappop(self._queue)
            self.admit(item.key, now=now, cost=item.cost, priority=-item.priority, quota=item.quota)
            out.append(item.key)
        return out

    # -- observability ---------------------------------------------------------
    def snapshot(self, *, now: float) -> dict:
        return {
            'policy': self.policy,
            'queue_depth': len(self._queue),
            'queue_limit': self.queue_limit,
            'admitted': self.admitted,
            'rejected': self.rejected,
            'shed': self.shed,
            'quotas': {name: {'tokens': round(q.bucket.tokens, 3), 'rate': q.rate,
                              'burst': q.burst, 'parent': q.parent.name if q.parent else None}
                       for name, q in self._quotas.items()},
            'recent': self._recent.items(),
        }

    def _queue_keys(self) -> set[str]:
        return {item.key for item in self._queue}

    @staticmethod
    def _deficit(quota: Quota, now: float, cost: float) -> float:
        bucket = quota.bucket
        available = min(bucket.burst, bucket.tokens + max(0.0, now - bucket.time) * bucket.rate)
        return max(0.0, cost - available)
