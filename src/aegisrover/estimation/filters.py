"""Kalman filtering with gating, Joseph-form covariance and consistency reporting.

Two things make a filter trustworthy in the field. Measurements that are physically
implausible must be *rejected and reported* instead of being folded into the state,
and the covariance must stay symmetric and positive semi-definite — the Joseph form
update keeps the numerical properties even after thousands of steps. Consistency
reporting (NEES) tells an operator when the filter is overconfident instead of
silently diverging.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

__all__ = ('UpdateReport', 'ConsistencyReport', 'KalmanFilter', 'mahalanobis_squared')


@dataclass(frozen=True)
class UpdateReport:
    accepted: bool
    distance: float
    threshold: float
    reason: str = ''

    def to_dict(self) -> dict:
        return {'accepted': self.accepted, 'distance': round(self.distance, 6),
                'threshold': self.threshold, 'reason': self.reason}


@dataclass(frozen=True)
class ConsistencyReport:
    steps: int
    mean_nees: float
    dimension: int
    consistent: bool
    rejected: int = 0

    def to_dict(self) -> dict:
        return {'steps': self.steps, 'mean_nees': round(self.mean_nees, 6), 'dimension': self.dimension,
                'consistent': self.consistent, 'rejected': self.rejected}


def mahalanobis_squared(innovation: Sequence[float], covariance: np.ndarray) -> float:
    vector = np.asarray(innovation, dtype=float)
    matrix = np.asarray(covariance, dtype=float)
    try:
        solved = np.linalg.solve(matrix, vector)
    except np.linalg.LinAlgError:
        solved = np.linalg.pinv(matrix) @ vector
    return float(vector @ solved)


class KalmanFilter:
    def __init__(self, x: Sequence[float], P: np.ndarray, *, gate: float | None = None):
        self.x = np.asarray(x, dtype=float).reshape(-1)
        self.P = _symmetrise(np.asarray(P, dtype=float))
        if self.P.shape != (self.x.size, self.x.size):
            raise ValueError('P must match the state dimension')
        self.gate = gate
        self.updates: list[UpdateReport] = []
        self._nees: list[float] = []
        self.predictions = 0

    # -- model steps -----------------------------------------------------------
    def predict(self, F: np.ndarray, Q: np.ndarray | None = None) -> 'KalmanFilter':
        F = np.asarray(F, dtype=float)
        self.x = F @ self.x
        self.P = _symmetrise(F @ self.P @ F.T + (np.zeros_like(self.P) if Q is None else np.asarray(Q, dtype=float)))
        self.predictions += 1
        return self

    def update(self, z: Sequence[float], H: np.ndarray, R: np.ndarray, *,
               gate: float | None = None) -> UpdateReport:
        H = np.asarray(H, dtype=float)
        R = np.asarray(R, dtype=float)
        measurement = np.asarray(z, dtype=float).reshape(-1)
        innovation = measurement - H @ self.x
        S = _symmetrise(H @ self.P @ H.T + R)
        distance = mahalanobis_squared(innovation, S)
        limit = self.gate if gate is None else gate
        if limit is not None and distance > limit:
            report = UpdateReport(False, distance, float(limit), 'gated')
            self.updates.append(report)
            return report
        K = self.P @ H.T @ np.linalg.pinv(S)
        self.x = self.x + K @ innovation
        identity = np.eye(self.P.shape[0])
        # Joseph form keeps the covariance symmetric and PSD.
        self.P = _symmetrise((identity - K @ H) @ self.P @ (identity - K @ H).T + K @ R @ K.T)
        report = UpdateReport(True, distance, float('inf') if limit is None else float(limit))
        self.updates.append(report)
        return report

    # -- introspection ---------------------------------------------------------
    def consistency(self) -> ConsistencyReport:
        """Average normalised estimation error squared over accepted updates."""
        accepted = [u for u in self.updates if u.accepted]
        nees = [u.distance / max(1, self.x.size) for u in accepted]
        mean = float(np.mean(nees)) if nees else 0.0
        return ConsistencyReport(steps=len(self.updates), mean_nees=mean, dimension=self.x.size,
                                 consistent=0.1 <= mean <= 10.0 if nees else False,
                                 rejected=len(self.updates) - len(accepted))

    def covariance_is_healthy(self) -> bool:
        if not np.allclose(self.P, self.P.T, atol=1e-9):
            return False
        eigenvalues = np.linalg.eigvalsh(self.P)
        return bool(np.all(eigenvalues >= -1e-9)) and bool(np.all(np.isfinite(self.P)))

    def to_dict(self) -> dict:
        return {'x': [float(v) for v in self.x], 'P': self.P.tolist(),
                'predictions': self.predictions,
                'updates': [u.to_dict() for u in self.updates],
                'consistency': self.consistency().to_dict()}


def _symmetrise(matrix: np.ndarray) -> np.ndarray:
    return (matrix + matrix.T) / 2.0
