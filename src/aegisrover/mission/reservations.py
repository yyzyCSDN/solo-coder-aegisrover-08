from dataclasses import dataclass

@dataclass(frozen=True)
class Reservation:
    robot: str
    resource: str
    start: float
    end: float

def conflicts(a: Reservation, b: Reservation):
    return a.resource == b.resource and max(a.start, b.start) < min(a.end, b.end)

def can_reserve(existing, candidate):
    return not any((conflicts(r, candidate) for r in existing if r.robot != candidate.robot))

def reserve(existing, candidate):
    if not can_reserve(existing, candidate):
        raise ValueError('conflict')
    return [*existing, candidate]
