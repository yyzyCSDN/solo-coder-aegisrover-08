"""Hierarchical admission control with bounded queues and overload policies.

Quotas form a tree (fleet -> robot -> client). A request must pass every level before
any token is consumed, so a rejection never leaves a parent quota half-charged. When
the queue is full the configured policy decides whether the newest request is
rejected, the lowest-priority queued item is shed, or the caller is told to retry.

Quotas registered with enable_adaptive() are tuned by a closed loop instead of a
hand-set rate: each window the controller compares the observed reject ratio and
queue pressure against a target and nudges the token-bucket rate up or down
(additive increase, multiplicative decrease, clamped to [min_rate, max_rate]). If
overload persists across several windows the relief level escalates - the effective
queue limit is halved per level and the lowest-priority backlog is shed - so
sustained overload drains pressure instead of letting it pile up. Calm windows
restore one level at a time.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import Iterable

from .rate import TokenBucket
from .ring import Ring

__all__ = ('Quota', 'Admission', 'QueueItem', 'AdaptivePolicy', 'AdmissionController')


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


@dataclass(frozen=True)
class AdaptivePolicy:
    """Closed-loop tuning knobs for one quota's token-bucket rate.

    Each window the controller compares the quota's reject ratio against
    target_reject_ratio: overload cuts the rate multiplicatively, while a clean
    window that actually saturated the quota raises it additively. Rates stay
    clamped to [min_rate, max_rate]; those bounds are the safety rails, the loop
    finds the operating point between them on its own.
    """
    min_rate: float
    max_rate: float
    increase_step: float = 1.0
    decrease_factor: float = 0.5
    target_reject_ratio: float = 0.02
    increase_utilization: float = 0.8
    min_samples: int = 4


class AdmissionController:
    def __init__(self, *, queue_limit: int = 32, policy: str = 'reject', recent: int = 32,
                 window: float = 1.0, relief_after: int = 3, queue_floor: int = 4):
        if policy not in ('reject', 'shed_lowest', 'delay'):
            raise ValueError('unknown policy')
        if window <= 0:
            raise ValueError('window')
        self.queue_limit = queue_limit
        self.policy = policy
        self.window = window
        self.relief_after = max(1, relief_after)
        self.queue_floor = max(0, min(queue_floor, queue_limit))
        self.relief = 0
        self._quotas: dict[str, Quota] = {}
        self._queue: list[QueueItem] = []
        self._counter = itertools.count()
        self._recent = Ring(recent)
        self._adaptive: dict[str, AdaptivePolicy] = {}
        self._stats: dict[str, dict[str, int]] = {}
        self._window_start: float | None = None
        self._queue_full_events = 0
        self._overloaded_streak = 0
        self._calm_streak = 0
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
        self._maybe_tune(now)
        chain = self.quota(quota).chain()
        shortfall = [(q, self._deficit(q, now, cost)) for q in chain]
        blocked = [(q, deficit) for q, deficit in shortfall if deficit > 0]
        if blocked:
            self.rejected += 1
            self._record(blocked[0][0].name, 'rejected')
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
            self._record(bucket_quota.name, 'admitted')
        self.admitted += 1
        return Admission(True, '', 0.0, tuple(q.name for q in chain))

    def enqueue(self, key: str, *, now: float, cost: float = 1.0, priority: int = 0,
                quota: str = 'global') -> Admission:
        self._maybe_tune(now)
        if len(self._queue) >= self.effective_queue_limit:
            self._queue_full_events += 1
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

    # -- adaptive tuning -------------------------------------------------------
    def enable_adaptive(self, name: str, policy: AdaptivePolicy) -> None:
        """Register a quota for closed-loop rate tuning within policy bounds."""
        quota = self.quota(name)
        if not policy.min_rate <= quota.bucket.rate <= policy.max_rate:
            raise ValueError('current rate outside policy bounds')
        self._adaptive[name] = policy
        self._stats.setdefault(name, {'admitted': 0, 'rejected': 0})

    def tune(self, *, now: float) -> dict[str, float]:
        """Close the current window and adjust adaptive rates and relief level.

        Returns the new rate of every adaptive quota. Safe to call any time; it
        only acts once a full window has elapsed.
        """
        if self._window_start is None:
            self._window_start = now
            return {}
        elapsed = now - self._window_start
        if elapsed < self.window:
            return {}
        overloaded = self._queue_full_events > 0
        rates = {}
        for name, policy in self._adaptive.items():
            stats = self._stats.get(name, {'admitted': 0, 'rejected': 0})
            total = stats['admitted'] + stats['rejected']
            quota = self._quotas[name]
            rate = quota.bucket.rate
            if total >= policy.min_samples:
                if stats['rejected'] / total > policy.target_reject_ratio:
                    rate = max(policy.min_rate, rate * policy.decrease_factor)
                    overloaded = True
                elif stats['admitted'] >= rate * elapsed * policy.increase_utilization:
                    # only probe upward when demand actually saturated the quota,
                    # otherwise an idle window would drift the rate to max_rate
                    rate = min(policy.max_rate, rate + policy.increase_step)
            quota.bucket.rate = rate
            rates[name] = rate
        if overloaded:
            self._calm_streak = 0
            self._overloaded_streak += 1
            if self._overloaded_streak >= self.relief_after:
                self._overloaded_streak = 0
                self.relief += 1
                self._shed_to_limit(now)
        else:
            self._overloaded_streak = 0
            self._calm_streak += 1
            if self.relief > 0 and self._calm_streak >= self.relief_after:
                self._calm_streak = 0
                self.relief -= 1
        self._reset_window(now)
        return rates

    @property
    def effective_queue_limit(self) -> int:
        """Queue capacity after relief escalation (halved per level, floored)."""
        return max(self.queue_floor, self.queue_limit >> self.relief)

    def _maybe_tune(self, now: float) -> None:
        if self._window_start is None:
            self._window_start = now
        elif now - self._window_start >= self.window:
            self.tune(now=now)

    def _reset_window(self, now: float) -> None:
        self._window_start = now
        self._queue_full_events = 0
        self._stats = {name: {'admitted': 0, 'rejected': 0} for name in self._adaptive}

    def _record(self, quota: str, field: str) -> None:
        stats = self._stats.get(quota)
        if stats is not None:
            stats[field] += 1

    def _shed_to_limit(self, now: float) -> None:
        """Drop the lowest-priority backlog beyond the effective queue limit."""
        while len(self._queue) > self.effective_queue_limit:
            victim = max(self._queue, key=lambda item: (item.priority, -item.sequence))
            self._queue.remove(victim)
            self.shed += 1
            self._recent.append({'at': now, 'key': victim.key, 'reason': 'relief_shed'})
        heapq.heapify(self._queue)

    # -- observability ---------------------------------------------------------
    def snapshot(self, *, now: float) -> dict:
        return {
            'policy': self.policy,
            'queue_depth': len(self._queue),
            'queue_limit': self.queue_limit,
            'effective_queue_limit': self.effective_queue_limit,
            'relief': self.relief,
            'admitted': self.admitted,
            'rejected': self.rejected,
            'shed': self.shed,
            'adaptive': {name: {'rate': round(self._quotas[name].bucket.rate, 6),
                                'min_rate': p.min_rate, 'max_rate': p.max_rate}
                         for name, p in self._adaptive.items()},
            'quotas': {name: {'tokens': round(q.bucket.tokens, 3), 'rate': q.bucket.rate,
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
