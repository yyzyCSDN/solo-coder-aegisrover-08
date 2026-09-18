"""Capability negotiation between a client and a robot.

Rules: the capability name must match, the major version must match exactly, the
offered minor version must be at least the requested one (minor versions only add
features), and every *required* feature must be present. Optional requirements are
reported as degraded instead of failing the whole negotiation, so a client can
decide whether it still wants to run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

__all__ = ('Requirement', 'Offer', 'Rejection', 'Negotiation', 'NegotiationError', 'negotiate')


@dataclass(frozen=True)
class Requirement:
    name: str
    major: int
    minor: int = 0
    features: frozenset[str] = frozenset()
    optional: bool = False


@dataclass(frozen=True)
class Offer:
    name: str
    major: int
    minor: int = 0
    features: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Rejection:
    name: str
    reason: str
    detail: str


@dataclass(frozen=True)
class Negotiation:
    accepted: dict[str, Offer] = field(default_factory=dict)
    degraded: tuple[Rejection, ...] = ()
    rejected: tuple[Rejection, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.rejected

    def require_ok(self) -> 'Negotiation':
        if not self.ok:
            raise NegotiationError(self.rejected)
        return self

    def to_dict(self) -> dict:
        return {
            'ok': self.ok,
            'accepted': {name: {'major': o.major, 'minor': o.minor, 'features': sorted(o.features)}
                         for name, o in self.accepted.items()},
            'degraded': [r.__dict__ for r in self.degraded],
            'rejected': [r.__dict__ for r in self.rejected],
        }


class NegotiationError(RuntimeError):
    def __init__(self, rejections: Iterable[Rejection]):
        self.rejections = tuple(rejections)
        super().__init__('; '.join(f'{r.name}: {r.reason}' for r in self.rejections))


def negotiate(requirements: Iterable[Requirement], offers: Iterable[Offer]) -> Negotiation:
    pool: dict[str, list[Offer]] = {}
    for offer in offers:
        pool.setdefault(offer.name, []).append(offer)
    accepted: dict[str, Offer] = {}
    degraded: list[Rejection] = []
    rejected: list[Rejection] = []
    for requirement in requirements:
        candidates = pool.get(requirement.name, [])
        choice, reason, detail = _select(requirement, candidates)
        if choice is not None:
            accepted[requirement.name] = choice
            missing = requirement.features - choice.features
            if requirement.optional and missing:
                degraded.append(Rejection(requirement.name, 'missing_optional_features',
                                          ','.join(sorted(missing))))
            continue
        if requirement.optional:
            reason = reason if reason == 'missing_optional_features' else 'missing_optional_features'
        problem = Rejection(requirement.name, reason, detail)
        (degraded if requirement.optional else rejected).append(problem)
    return Negotiation(accepted=accepted, degraded=tuple(degraded), rejected=tuple(rejected))


def _select(requirement: Requirement, candidates: list[Offer]) -> tuple[Offer | None, str, str]:
    if not candidates:
        return None, 'not_offered', 'robot does not provide this capability'
    same_major = [c for c in candidates if c.major == requirement.major]
    if not same_major:
        majors = ','.join(sorted({str(c.major) for c in candidates}))
        return None, 'major_mismatch', f'offered majors {majors}, need {requirement.major}'
    usable = [c for c in same_major if c.minor >= requirement.minor and requirement.features <= c.features]
    if not usable:
        newest = max(same_major, key=lambda c: c.minor)
        missing = ','.join(sorted(requirement.features - newest.features))
        if newest.minor < requirement.minor:
            return None, 'minor_too_old', f'offered {newest.minor}, need {requirement.minor}'
        return None, 'missing_features', missing
    return max(usable, key=lambda c: c.minor), '', ''
