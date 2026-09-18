"""Sensor calibration and fusion with age-aware weighting.

Measurements arrive with different ages and different noise levels. Fusing them with
equal weight is how a stale reading keeps steering the estimate, so each sample is
weighted by both its variance and its freshness (an exponential half-life), and the
agreement between sources is reported: a low agreement score means at least one
sensor is wrong and the operator should look before trusting the fused value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from aegisrover.estimation.outliers import hampel

__all__ = ('Calibration', 'CalibrationError', 'Measurement', 'FusionResult',
           'fit_calibration', 'align_series', 'fuse', 'agreement')


class CalibrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Calibration:
    scale: float
    offset: float
    samples: int
    rms_residual: float
    max_residual: float
    rejected: tuple[int, ...] = ()

    def apply(self, value: float) -> float:
        return self.scale * float(value) + self.offset

    def apply_many(self, values: Sequence[float]) -> list[float]:
        return [self.apply(v) for v in values]

    def to_dict(self) -> dict:
        return {'scale': self.scale, 'offset': self.offset, 'samples': self.samples,
                'rms_residual': round(self.rms_residual, 9),
                'max_residual': round(self.max_residual, 9),
                'rejected': list(self.rejected)}


def fit_calibration(raw: Sequence[float], truth: Sequence[float], *,
                    tolerance: float | None = None, reject_outliers: bool = True) -> Calibration:
    if len(raw) != len(truth) or len(raw) < 2:
        raise CalibrationError('need at least two raw/truth pairs')
    x = np.asarray(raw, dtype=float)
    y = np.asarray(truth, dtype=float)
    rejected: tuple[int, ...] = ()
    if reject_outliers and len(x) >= 3:
        # A single bad sample can drag a least-squares line far enough that its own
        # residual is no longer the largest one, so the search starts from a robust
        # Theil-Sen estimate (median of pairwise slopes) instead.
        slopes = [(y[j] - y[i]) / (x[j] - x[i])
                  for i in range(len(x)) for j in range(i + 1, len(x)) if x[j] != x[i]]
        if slopes:
            slope = float(np.median(slopes))
            offset = float(np.median(y - slope * x))
            residuals = y - (slope * x + offset)
            flags = hampel(list(residuals))
            if not any(flags):
                # Median absolute deviation collapses to zero for a perfect fit, so
                # fall back to a scaled absolute threshold.
                limit = max(3.0 * float(np.median(np.abs(residuals))), 1e-6 * max(1.0, float(np.max(np.abs(y)))))
                flags = [abs(float(r)) > limit for r in residuals]
            rejected = tuple(i for i, bad in enumerate(flags) if bad)
            if len(rejected) >= len(x) - 1:
                rejected = ()
            if rejected:
                keep = [i for i in range(len(x)) if i not in rejected]
                x, y = x[keep], y[keep]
    if len(x) < 2:
        raise CalibrationError('too few samples after outlier rejection')
    scale, offset = (float(v) for v in np.polyfit(x, y, 1))
    residuals = y - (scale * x + offset)
    rms = float(math.sqrt(float(np.mean(residuals ** 2))))
    maximum = float(np.max(np.abs(residuals)))
    if tolerance is not None and rms > tolerance:
        raise CalibrationError(f'calibration residual {rms:.6f} exceeds tolerance {tolerance}')
    return Calibration(scale, offset, len(x), rms, maximum, rejected)


def align_series(times: Sequence[float], values: Sequence[float], targets: Iterable[float], *,
                 extrapolate: bool = False) -> list[float | None]:
    """Linear interpolation onto ``targets``; outside the window returns ``None``."""
    if len(times) != len(values):
        raise ValueError('times and values must have the same length')
    if len(times) < 2:
        raise ValueError('need at least two samples')
    pairs = sorted(zip(times, values))
    ts = [p[0] for p in pairs]
    vs = [p[1] for p in pairs]
    out: list[float | None] = []
    for target in targets:
        if target < ts[0] or target > ts[-1]:
            if not extrapolate:
                out.append(None)
                continue
            if target < ts[0]:
                out.append(vs[0])
                continue
            out.append(vs[-1])
            continue
        for i in range(len(ts) - 1):
            if ts[i] <= target <= ts[i + 1]:
                span = ts[i + 1] - ts[i]
                if span <= 1e-12:
                    out.append(vs[i])
                else:
                    f = (target - ts[i]) / span
                    out.append(vs[i] + f * (vs[i + 1] - vs[i]))
                break
    return out


@dataclass(frozen=True)
class Measurement:
    source: str
    value: float
    variance: float
    age: float = 0.0

    def __post_init__(self):
        if self.variance <= 0:
            raise ValueError('variance must be positive')
        if self.age < 0:
            raise ValueError('age must not be negative')


@dataclass(frozen=True)
class FusionResult:
    value: float
    weights: dict[str, float]
    agreement: float
    rejected: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {'value': round(self.value, 9),
                'weights': {k: round(v, 6) for k, v in self.weights.items()},
                'agreement': round(self.agreement, 6),
                'rejected': list(self.rejected), 'stale': list(self.stale)}


def agreement(values: Sequence[float]) -> float:
    """1.0 when every source agrees, 0.0 when the spread dwarfs the value."""
    if len(values) < 2:
        return 1.0
    mean = sum(values) / len(values)
    spread = max(values) - min(values)
    scale = abs(mean) + 1e-9
    return max(0.0, 1.0 - spread / (spread + scale))


def fuse(measurements: Sequence[Measurement], *, half_life: float | None = None,
         now: float | None = None, max_age: float | None = None) -> FusionResult:
    if not measurements:
        raise ValueError('at least one measurement is required')
    rejected: list[str] = []
    stale: list[str] = []
    kept: list[Measurement] = []
    for item in measurements:
        if max_age is not None and item.age > max_age:
            stale.append(item.source)
            continue
        kept.append(item)
    if not kept:
        raise ValueError('all measurements are stale')
    if len(kept) >= 3:
        flags = hampel([m.value for m in kept])
        survivors = [m for m, bad in zip(kept, flags) if not bad]
        if survivors:
            rejected = [m.source for m, bad in zip(kept, flags) if bad]
            kept = survivors
    weights: dict[str, float] = {}
    total = 0.0
    for item in kept:
        weight = 1.0 / item.variance
        if half_life is not None:
            weight *= math.pow(0.5, item.age / half_life)
        weights[item.source] = weight
        total += weight
    if total <= 0:
        raise ValueError('fused weight is zero')
    value = sum(weights[m.source] * m.value for m in kept) / total
    normalised = {k: v / total for k, v in weights.items()}
    return FusionResult(value, normalised, agreement([m.value for m in kept]),
                        tuple(rejected), tuple(stale))
