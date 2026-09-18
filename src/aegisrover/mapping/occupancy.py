"""Log-odds occupancy grid with scan integration.

Cells hold log-odds instead of a probability so repeated hits and misses compose by
addition and stay clamped to a configurable confidence band. Integrating a scan
marks the traversed cells as free and only the beam endpoint as occupied: a beam
that reaches the sensor's maximum range says "nothing was seen out there", which is
evidence about free space, not about an obstacle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from aegisrover.core.types import GridShape, Pose2, Vec2
from aegisrover.mapping.raycast import bresenham

__all__ = ('ScanReport', 'LogOddsGrid')

LOGIT_HIT = math.log(0.7 / 0.3)
LOGIT_MISS = math.log(0.4 / 0.6)


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


@dataclass(frozen=True)
class ScanReport:
    beams: int
    free_marked: int
    occupied_marked: int
    skipped: int
    changed: int

    def to_dict(self) -> dict:
        return {'beams': self.beams, 'free_marked': self.free_marked,
                'occupied_marked': self.occupied_marked, 'skipped': self.skipped,
                'changed': self.changed}


@dataclass
class LogOddsGrid:
    shape: GridShape
    prior: float = 0.5
    lower: float = 0.02
    upper: float = 0.98
    revision: int = 0
    _values: list[float] = field(default_factory=list)

    def __post_init__(self):
        self.shape.validate()
        if not (0.0 < self.prior < 1.0):
            raise ValueError('prior must be a probability')
        if not 0.0 < self.lower < self.upper < 1.0:
            raise ValueError('invalid confidence band')
        if not self._values:
            self._values = [self._logit(self.prior)] * (self.shape.width * self.shape.height)
        elif len(self._values) != self.shape.width * self.shape.height:
            raise ValueError('cell count does not match the grid shape')

    # -- cell access -----------------------------------------------------------
    def index(self, x: int, y: int) -> int:
        if not (0 <= x < self.shape.width and 0 <= y < self.shape.height):
            raise IndexError((x, y))
        return y * self.shape.width + x

    def world_to_cell(self, point: Vec2) -> tuple[int, int]:
        """World point to cell index; uses floor so negative coordinates stay ordered."""
        x = math.floor((point.x - self.shape.origin.x) / self.shape.resolution)
        y = math.floor((point.y - self.shape.origin.y) / self.shape.resolution)
        return (int(x), int(y))

    def probability(self, x: int, y: int) -> float:
        return self._logistic(self._values[self.index(x, y)])

    def is_occupied(self, x: int, y: int, *, threshold: float = 0.6) -> bool:
        return self.probability(x, y) >= threshold

    def is_free(self, x: int, y: int, *, threshold: float = 0.4) -> bool:
        return self.probability(x, y) <= threshold

    def update(self, x: int, y: int, occupied: bool, *, p_hit: float = 0.7,
               p_miss: float = 0.4) -> float:
        delta = math.log(p_hit / (1 - p_hit)) if occupied else math.log(p_miss / (1 - p_miss))
        i = self.index(x, y)
        value = _clamp(self._values[i] + delta,
                       self._logit(self.lower), self._logit(self.upper))
        changed = value != self._values[i]
        self._values[i] = value
        if changed:
            self.revision += 1
        return self._logistic(value)

    # -- scan integration ------------------------------------------------------
    def integrate_scan(self, pose: Pose2, ranges: Sequence[float], *, angle_min: float = -math.pi,
                       angle_increment: float = math.pi / 180.0, max_range: float = 10.0,
                       min_range: float = 0.05, p_hit: float = 0.7) -> ScanReport:
        free = occupied = skipped = changed = 0
        start = self.world_to_cell(pose.position)
        for index, distance in enumerate(ranges):
            if distance is None or not math.isfinite(distance) or distance < min_range:
                skipped += 1
                continue
            angle = pose.yaw + angle_min + index * angle_increment
            reach = min(float(distance), max_range)
            end_point = Vec2(pose.x + reach * math.cos(angle), pose.y + reach * math.sin(angle))
            end_cell = self.world_to_cell(end_point)
            ray = bresenham(*start, *end_cell)
            hit = float(distance) < max_range
            for cell in ray[:-1] if hit else ray:
                if self._inside(cell):
                    before = self._values[self.index(*cell)]
                    self.update(cell[0], cell[1], False, p_miss=0.4)
                    free += 1
                    changed += int(self._values[self.index(*cell)] != before)
            if hit and ray and self._inside(ray[-1]):
                before = self._values[self.index(*ray[-1])]
                self.update(ray[-1][0], ray[-1][1], True, p_hit=p_hit)
                occupied += 1
                changed += int(self._values[self.index(*ray[-1])] != before)
        if changed:
            self.revision += 1
        return ScanReport(len(ranges), free, occupied, skipped, changed)

    # -- aggregate statistics --------------------------------------------------
    def coverage(self, *, free_threshold: float = 0.4, occupied_threshold: float = 0.6) -> float:
        known = sum(1 for value in self._values
                    if self._logistic(value) <= free_threshold or self._logistic(value) >= occupied_threshold)
        return known / len(self._values)

    def entropy(self) -> float:
        total = 0.0
        for value in self._values:
            p = self._logistic(value)
            if 0.0 < p < 1.0:
                total -= p * math.log2(p) + (1 - p) * math.log2(1 - p)
        return total / len(self._values)

    def occupied_cells(self, *, threshold: float = 0.6) -> tuple[tuple[int, int], ...]:
        return tuple((x, y) for y in range(self.shape.height) for x in range(self.shape.width)
                     if self.is_occupied(x, y, threshold=threshold))

    def stats(self) -> dict:
        return {'revision': self.revision, 'coverage': round(self.coverage(), 6),
                'entropy': round(self.entropy(), 6),
                'occupied': len(self.occupied_cells())}

    # -- persistence -----------------------------------------------------------
    def to_payload(self) -> dict:
        return {
            'width': self.shape.width,
            'height': self.shape.height,
            'resolution': self.shape.resolution,
            'origin': [self.shape.origin.x, self.shape.origin.y],
            'prior': self.prior,
            'lower': self.lower,
            'upper': self.upper,
            'revision': self.revision,
            'values': [round(v, 9) for v in self._values],
        }

    @staticmethod
    def from_payload(payload: dict) -> 'LogOddsGrid':
        shape = GridShape(int(payload['width']), int(payload['height']), float(payload['resolution']),
                          Vec2(float(payload['origin'][0]), float(payload['origin'][1])))
        return LogOddsGrid(shape, prior=float(payload.get('prior', 0.5)),
                           lower=float(payload.get('lower', 0.02)),
                           upper=float(payload.get('upper', 0.98)),
                           revision=int(payload.get('revision', 0)),
                           _values=[float(v) for v in payload['values']])

    # -- helpers ---------------------------------------------------------------
    def _inside(self, cell: tuple[int, int]) -> bool:
        x, y = cell
        return 0 <= x < self.shape.width and 0 <= y < self.shape.height

    @staticmethod
    def _logit(p: float) -> float:
        return math.log(p / (1 - p))

    @staticmethod
    def _logistic(value: float) -> float:
        if value >= 0:
            z = math.exp(-value)
            return 1 / (1 + z)
        z = math.exp(value)
        return z / (1 + z)
