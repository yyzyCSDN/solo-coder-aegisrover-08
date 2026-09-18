from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable
import math

@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: 'Vec2') -> 'Vec2':
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: 'Vec2') -> 'Vec2':
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, k: float) -> 'Vec2':
        return Vec2(self.x * k, self.y * k)

    def dot(self, other: 'Vec2') -> float:
        return self.x * other.x + self.y * other.y

    def norm(self) -> float:
        return math.hypot(self.x, self.y)

    def distance(self, other: 'Vec2') -> float:
        return (self - other).norm()

@dataclass(frozen=True)
class Pose2:
    x: float
    y: float
    yaw: float

    @property
    def position(self) -> Vec2:
        return Vec2(self.x, self.y)

@dataclass(frozen=True)
class Twist2:
    linear: float
    angular: float

@dataclass(frozen=True)
class TimedPose:
    time: float
    pose: Pose2

@dataclass
class Diagnostic:
    code: str
    severity: str
    message: str
    data: dict = field(default_factory=dict)

@dataclass(frozen=True)
class GridShape:
    width: int
    height: int
    resolution: float
    origin: Vec2

    def validate(self):
        if self.width <= 0 or self.height <= 0 or self.resolution <= 0:
            raise ValueError('invalid grid')

@dataclass(frozen=True)
class Interval:
    start: float
    end: float

    def contains(self, value: float) -> bool:
        return self.start <= value <= self.end

    def overlap(self, other: 'Interval') -> float:
        return max(0.0, min(self.end, other.end) - max(self.start, other.start))

def wrap_angle(v: float) -> float:
    return (v + math.pi) % (2 * math.pi) - math.pi

def pairwise(values: Iterable):
    it = iter(values)
    prev = next(it, None)
    for cur in it:
        yield (prev, cur)
        prev = cur
