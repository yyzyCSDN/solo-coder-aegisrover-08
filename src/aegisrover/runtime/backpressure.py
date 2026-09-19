"""Hierarchical admission control with bounded queues and overload policies.

Quotas form a tree (fleet -> robot -> client). A request must pass every level before
any token is consumed, so a rejection never leaves a parent quota half-charged. When
the queue is full the configured policy decides whether the newest request is
rejected, the lowest-priority queued item is shed, or the caller is told to retry.

Quota rates can also tune themselves instead of waiting for manual adjustment: with
an AdaptiveConfig the controller re-evaluates every window, raising rates additively
while the queue drains and cutting them multiplicatively when the queue backs up or
turns requests away (AIMD, as in TCP congestion control). Rejections against a quota
with an empty queue mean unmet demand, not overload, so they never push the rate
down. If the queue stays above its target occupancy for a sustained interval, queued
work is shed lowest-priority-first at an escalating cadence, so persistent overload
drains away instead of piling up (CoDel-style active queue management).
"""
from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass, field

from .rate import TokenBucket
from .ring import Ring

__all__ = ('Quota', 'Admission', 'QueueItem', 'AdaptiveConfig', 'AdmissionController')


@dataclass
class Quota:
    name: str
    rate: float
    burst: float
    parent: 'Quota | None' = None
    min_rate: float | None = None
    max_rate: float | None = None
    bucket: TokenBucket = field(init=False, repr=False)
    children: list['Quota'] = field(default_factory=list, repr=False)

    def __post_init__(self):
        if (self.min_rate is None) != (self.max_rate is None):
            raise ValueError('min_rate and max_rate must be set together')
        if self.min_rate is not None:
            if not 0 <= self.min_rate <= self.max_rate:
                raise ValueError('require 0 <= min_rate <= max_rate')
            self.rate = min(max(self.rate, self.min_rate), self.max_rate)
        self.bucket = TokenBucket(self.rate, self.burst)
        if self.parent is not None:
            self.parent.children.append(self)

    def chain(self) -> list['Quota']:
        node, out = self, []
        while node is not None:
            out.append(node)
            node = node.parent
        return out

    @property
    def adaptive(self) -> bool:
        return self.min_rate is not None


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


@dataclass
class AdaptiveConfig:
    """Tuning for automatic quota rates and sustained-overload relief.

    Every ``window`` seconds each adaptive quota's rate grows by ``increase``
    (tokens/s, additive), or is multiplied by ``decrease`` while the queue sits
    above ``queue_target`` occupancy or arrivals are turned away from a full
    queue. Rejections against a quota with an empty queue mean unmet demand,
    not overload, so they never push the rate down. If the queue stays above
    target for ``overload_interval`` seconds, queued items are shed
    lowest-priority-first every ``shed_interval / sqrt(n)`` seconds until
    occupancy returns to target, so a persistent flood drains instead of
    accumulating.
    """

    window: float = 1.0
    increase: float = 1.0
    decrease: float = 0.5
    queue_target: float = 0.5
    overload_interval: float = 5.0
    shed_interval: float = 1.0

    def __post_init__(self):
        if self.window <= 0:
            raise ValueError('window must be positive')
        if self.increase <= 0:
            raise ValueError('increase must be positive')
        if not 0 < self.decrease < 1:
            raise ValueError('decrease must be in (0, 1)')
        if not 0 <= self.queue_target <= 1:
            raise ValueError('queue_target must be in [0, 1]')
        if self.overload_interval < 0:
            raise ValueError('overload_interval must be >= 0')
        if self.shed_interval <= 0:
            raise ValueError('shed_interval must be positive')


class AdmissionController:
    def __init__(self, *, queue_limit: int = 32, policy: str = 'reject', recent: int = 32,
                 adaptive: AdaptiveConfig | None = None):
        if policy not in ('reject', 'shed_lowest', 'delay'):
            raise ValueError('unknown policy')
        self.queue_limit = queue_limit
        self.policy = policy
        self.adaptive = adaptive
        self._quotas: dict[str, Quota] = {}
        self._queue: list[QueueItem] = []
        self._counter = itertools.count()
        self._recent = Ring(recent)
        self.admitted = 0
        self.rejected = 0
        self.shed = 0
        self._queue_full = 0
        self._next_update_at: float | None = None
        self._overload_since: float | None = None
        self._shed_count = 0
        self._next_shed_at = 0.0

    # -- setup -----------------------------------------------------------------
    def add_quota(self, name: str, rate: float, burst: float, parent: str | None = None,
                  *, min_rate: float | None = None, max_rate: float | None = None) -> Quota:
        if name in self._quotas:
            raise ValueError(f'quota {name!r} already registered')
        parent_quota = None if parent is None else self._quotas.get(parent)
        if parent is not None and parent_quota is None:
            raise ValueError(f'unknown parent quota {parent!r}')
        if min_rate is not None and self.adaptive is None:
            raise ValueError('adaptive quota bounds require adaptive=AdaptiveConfig(...)')
        quota = Quota(name, rate, burst, parent_quota, min_rate, max_rate)
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
        self._maybe_update(now)
        chain = self.quota(quota).chain()
        shortfall = [(q, self._deficit(q, now, cost)) for q in chain]
        blocked = [(q, deficit) for q, deficit in shortfall if deficit > 0]
        if blocked:
            self.rejected += 1
            name = blocked[0][0].name
            self._recent.append({'at': now, 'key': key, 'reason': 'quota',
                                 'quota': name})
            wait = max(deficit / (q.rate or 1.0) for q, deficit in blocked)
            if self.policy == 'delay':
                return Admission(False, 'delayed', wait, tuple())
            return Admission(False, f'quota:{name}', wait, tuple())
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
                victim = self._shed_victim()
                if -victim.priority < priority:
                    self._queue.remove(victim)
                    heapq.heapify(self._queue)
                    self.shed += 1
                else:
                    self.rejected += 1
                    self._queue_full += 1
                    self._recent.append({'at': now, 'key': key, 'reason': 'queue_full'})
                    return Admission(False, 'queue_full', 0.0, tuple())
            else:
                self.rejected += 1
                self._queue_full += 1
                self._recent.append({'at': now, 'key': key, 'reason': 'queue_full'})
                return Admission(False, 'queue_full', 0.0, tuple())
        admitted = self.admit(key, now=now, cost=cost, quota=quota, priority=priority)
        if admitted.allowed:
            heapq.heappush(self._queue, QueueItem(-priority, next(self._counter), key, cost, quota))
        return admitted

    def pop_ready(self, *, now: float, limit: int = 1) -> list[str]:
        """Pop queued keys, highest priority first, up to ``limit``.

        Queued items were already charged at enqueue time, so draining is paced
        only by ``limit``; re-charging here would starve the backlog exactly
        when sustained overload demands relief.
        """
        self._maybe_update(now)
        out: list[str] = []
        while self._queue and len(out) < limit:
            out.append(heapq.heappop(self._queue).key)
        return out

    # -- adaptation --------------------------------------------------------------
    def update(self, *, now: float) -> dict:
        """Re-tune adaptive quotas and relieve sustained overload.

        Runs automatically from admit()/enqueue()/pop_ready(), so rates follow
        traffic on their own; it may also be called from a timer. Rates are
        re-tuned once per adaptive window, while overload detection and shedding
        are checked on every call.
        """
        cfg = self.adaptive
        shed: list[str] = []
        if cfg is not None:
            target = cfg.queue_target * self.queue_limit
            queue_hot = len(self._queue) > target
            if self._next_update_at is None:
                self._next_update_at = now + cfg.window
            elif now >= self._next_update_at:
                for quota in self._quotas.values():
                    if not quota.adaptive:
                        continue
                    if queue_hot or self._queue_full:
                        rate = max(quota.min_rate, quota.bucket.rate * cfg.decrease)
                    else:
                        rate = min(quota.max_rate, quota.bucket.rate + cfg.increase)
                    quota.rate = quota.bucket.rate = rate
                self._queue_full = 0
                self._next_update_at = now + cfg.window
            if queue_hot:
                if self._overload_since is None:
                    self._overload_since = now
                    self._shed_count = 0
                    self._next_shed_at = now + cfg.overload_interval
                while len(self._queue) > target and now >= self._next_shed_at:
                    victim = self._shed_victim()
                    self._queue.remove(victim)
                    heapq.heapify(self._queue)
                    self.shed += 1
                    shed.append(victim.key)
                    self._recent.append({'at': now, 'key': victim.key, 'reason': 'shed_overload'})
                    self._shed_count += 1
                    self._next_shed_at += cfg.shed_interval / math.sqrt(self._shed_count)
            else:
                self._overload_since = None
                self._shed_count = 0
        return {
            'now': now,
            'queue_depth': len(self._queue),
            'overloaded': self._overload_since is not None,
            'shed': shed,
            'rates': {q.name: q.bucket.rate for q in self._quotas.values() if q.adaptive},
        }

    # -- observability ---------------------------------------------------------
    def snapshot(self, *, now: float) -> dict:
        snap = {
            'policy': self.policy,
            'queue_depth': len(self._queue),
            'queue_limit': self.queue_limit,
            'admitted': self.admitted,
            'rejected': self.rejected,
            'shed': self.shed,
            'quotas': {name: {'tokens': round(q.bucket.tokens, 3), 'rate': q.bucket.rate,
                              'burst': q.burst, 'parent': q.parent.name if q.parent else None}
                       for name, q in self._quotas.items()},
            'recent': self._recent.items(),
        }
        if self.adaptive is not None:
            snap['adaptive'] = {
                'overloaded': self._overload_since is not None,
                'overload_since': self._overload_since,
                'limits': {q.name: {'min': q.min_rate, 'max': q.max_rate}
                           for q in self._quotas.values() if q.adaptive},
            }
        return snap

    def _maybe_update(self, now: float) -> None:
        if self.adaptive is not None:
            self.update(now=now)

    def _shed_victim(self) -> QueueItem:
        # QueueItem.priority is stored negated so heapq pops the highest
        # priority first; the victim is the item with the *lowest* real priority.
        return max(self._queue, key=lambda item: (item.priority, -item.sequence))

    def _queue_keys(self) -> set[str]:
        return {item.key for item in self._queue}

    @staticmethod
    def _deficit(quota: Quota, now: float, cost: float) -> float:
        bucket = quota.bucket
        available = min(bucket.burst, bucket.tokens + max(0.0, now - bucket.time) * bucket.rate)
        return max(0.0, cost - available)
