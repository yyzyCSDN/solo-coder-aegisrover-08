"""Clock estimation and monotonic event ordering.

The remote clock of a robot and the local clock of the control station differ by a
fixed offset plus a slowly changing drift. Stored event order must not depend on the
wall clock (NTP can step it backwards), so ordering uses the monotonic stamp with a
sequence number as tie-breaker, while the wall clock is kept for display only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

__all__ = ('ClockSample', 'ClockModel', 'ClockQuality', 'estimate', 'MonotonicOrder', 'OrderedEvent')


@dataclass(frozen=True)
class ClockSample:
    remote: float
    local: float


@dataclass(frozen=True)
class ClockModel:
    offset: float = 0.0
    drift: float = 0.0
    reference_remote: float = 0.0

    def remote_to_local(self, t: float) -> float:
        return t + self.offset + self.drift * (t - self.reference_remote)

    def local_to_remote(self, t: float) -> float:
        if abs(1 + self.drift) < 1e-12:
            raise ValueError('clock model is degenerate')
        return self.reference_remote + (t - self.reference_remote - self.offset) / (1 + self.drift)


@dataclass(frozen=True)
class ClockQuality:
    samples: int
    used: int
    rejected: tuple[int, ...] = ()
    rms_error: float = 0.0
    max_error: float = 0.0
    drift_ppm: float = 0.0


def estimate(pairs: Iterable[tuple[float, float]] | Iterable[ClockSample], *,
             robust: bool = True, max_residual: float = 0.05,
             max_drop_fraction: float = 0.25) -> tuple[ClockModel, ClockQuality]:
    """Fit ``local = f(remote)`` and report fit quality.

    With ``robust=True`` the worst residual is dropped when it is both larger than
    ``max_residual`` and at least three times the median residual of the remaining
    samples; the fit is then repeated. At most ``max_drop_fraction`` of the samples
    may be dropped, so a link that is consistently bad does not silently lose data.
    Dropped indices are reported in :class:`ClockQuality`.
    """
    samples = [p if isinstance(p, ClockSample) else ClockSample(float(p[0]), float(p[1])) for p in pairs]
    if len(samples) < 2:
        raise ValueError('need at least two clock samples')
    if len({s.remote for s in samples}) < 2:
        raise ValueError('clock samples must span more than one remote instant')
    kept = list(samples)
    rejected: list[int] = []
    budget = int(len(samples) * max_drop_fraction)
    model = _fit(kept)
    while robust and len(rejected) < budget and len(kept) > 3:
        residuals = [abs(s.local - model.remote_to_local(s.remote)) for s in kept]
        worst = max(range(len(kept)), key=lambda i: residuals[i])
        others = [r for i, r in enumerate(residuals) if i != worst]
        typical = _median(others) or 1e-9
        if residuals[worst] <= max(max_residual, 3.0 * typical):
            break
        rejected.append(samples.index(kept.pop(worst)))
        model = _fit(kept)
    errors = [abs(s.local - model.remote_to_local(s.remote)) for s in kept]
    quality = ClockQuality(
        samples=len(samples),
        used=len(kept),
        rejected=tuple(rejected),
        rms_error=math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else 0.0,
        max_error=max(errors) if errors else 0.0,
        drift_ppm=model.drift * 1e6,
    )
    return model, quality


def _fit(samples: Sequence[ClockSample]) -> ClockModel:
    n = len(samples)
    mx = sum(s.remote for s in samples) / n
    my = sum(s.local for s in samples) / n
    denom = sum((s.remote - mx) ** 2 for s in samples)
    if denom == 0:
        raise ValueError('degenerate clock samples')
    slope = sum((s.remote - mx) * (s.local - my) for s in samples) / denom
    intercept = my - slope * mx
    # Re-express the line so that the reference point is inside the sample window;
    # using a far-away reference is what made extrapolated timestamps drift.
    reference = mx
    offset = intercept + slope * reference - reference
    return ClockModel(offset=offset, drift=slope - 1.0, reference_remote=reference)


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


@dataclass(frozen=True)
class OrderedEvent:
    seq: int
    mono_ns: int
    wall_ns: int
    kind: str
    payload: dict = field(default_factory=dict)

    @property
    def order_key(self) -> tuple[int, int]:
        return (self.mono_ns, self.seq)


class MonotonicOrder:
    """Assigns display timestamps while ordering strictly by monotonic time.

    A wall clock step backwards (NTP correction) must not reorder events, and two
    events that share a monotonic stamp must keep arrival order.
    """

    def __init__(self):
        self._next_seq = 1
        self._last_mono = None
        self._events: list[OrderedEvent] = []
        self.wall_rollback = False
        self._last_wall = None

    def observe(self, mono_ns: int, wall_ns: int, kind: str, payload: dict | None = None) -> OrderedEvent:
        if self._last_mono is not None and mono_ns < self._last_mono:
            raise ValueError('monotonic timestamp moved backwards')
        if self._last_wall is not None and wall_ns < self._last_wall:
            self.wall_rollback = True
        event = OrderedEvent(self._next_seq, mono_ns, wall_ns, kind, dict(payload or {}))
        self._next_seq += 1
        self._last_mono = mono_ns
        self._last_wall = wall_ns
        self._events.append(event)
        return event

    def ordered(self) -> list[OrderedEvent]:
        return sorted(self._events, key=lambda e: e.order_key)

    def since(self, seq: int) -> list[OrderedEvent]:
        return [e for e in self.ordered() if e.seq > seq]

    def gaps(self) -> list[tuple[int, int]]:
        sequences = sorted(e.seq for e in self._events)
        return [(a, b) for a, b in zip(sequences, sequences[1:]) if b != a + 1]

    def stats(self) -> dict:
        return {'events': len(self._events), 'wall_rollback': self.wall_rollback,
                'gaps': self.gaps()}
