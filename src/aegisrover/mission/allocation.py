"""Time-window resource reservations for a fleet of robots.

Reservations are half-open intervals ``[start, end)``: a robot may take over a door
at exactly the instant the previous holder releases it, but two robots may never
hold the same resource over an overlapping window. Waiting robots are tracked in a
wait-for graph so a circular wait can be reported instead of deadlocking silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

__all__ = ('Reservation', 'Conflict', 'ReservationBook', 'Deadlock')


@dataclass(frozen=True, order=True)
class Reservation:
    resource: str
    holder: str
    start: float
    end: float
    mission_id: str = ''
    priority: int = 0

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError('reservation end must not precede start')
        if not self.resource or not self.holder:
            raise ValueError('resource and holder are required')

    def overlaps(self, other: 'Reservation') -> bool:
        return not (self.end <= other.start or other.end <= self.start)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {'resource': self.resource, 'holder': self.holder, 'start': self.start,
                'end': self.end, 'mission_id': self.mission_id, 'priority': self.priority}


class Conflict(RuntimeError):
    def __init__(self, reservation: Reservation, offenders: Iterable[Reservation]):
        self.reservation = reservation
        self.offenders = tuple(offenders)
        names = ', '.join(sorted({f'{o.holder}@{o.start:g}-{o.end:g}' for o in self.offenders}))
        super().__init__(f'{reservation.resource} busy for {reservation.holder}: {names}')


class Deadlock(RuntimeError):
    def __init__(self, cycle: Iterable[str]):
        self.cycle = tuple(cycle)
        super().__init__('circular wait: ' + ' -> '.join(self.cycle))


class ReservationBook:
    """In-memory reservation table with conflict and deadlock analysis."""

    def __init__(self):
        self._items: list[Reservation] = []
        self._waiting: dict[str, set[str]] = {}

    # -- reservation -----------------------------------------------------------
    def reserve(self, reservation: Reservation, *, preempt: bool = False,
                now: float | None = None) -> Reservation:
        """Reserve a window.

        With ``preempt=True`` a reservation may take a slot from lower-priority
        holders that have **not started yet** (``holder.start > now``). A holder
        that is already running is never evicted implicitly: the caller has to
        release it first, otherwise the conflict is reported.
        """
        offenders = [r for r in self._items if self._conflicting(r, reservation)]
        if offenders and preempt:
            horizon = reservation.start if now is None else now
            removable = [r for r in offenders
                         if r.priority < reservation.priority and r.start > horizon]
            if len(removable) == len(offenders):
                for item in removable:
                    self._items.remove(item)
                offenders = []
        if offenders:
            self._waiting.setdefault(reservation.holder, set()).update(o.holder for o in offenders)
            raise Conflict(reservation, offenders)
        self._items.append(reservation)
        self._waiting.pop(reservation.holder, None)
        return reservation

    def release(self, holder: str, *, resource: str | None = None) -> list[Reservation]:
        released = [r for r in self._items
                    if r.holder == holder and (resource is None or r.resource == resource)]
        self._items = [r for r in self._items if r not in released]
        return released

    def schedule(self, reservations: Iterable[Reservation]) -> list[Reservation]:
        """Reserve in priority order; raise the first conflict that cannot be solved."""
        accepted: list[Reservation] = []
        for item in sorted(reservations, key=lambda r: (-r.priority, r.start, r.holder)):
            self.reserve(item)
            accepted.append(item)
        return accepted

    # -- queries ---------------------------------------------------------------
    def items(self) -> tuple[Reservation, ...]:
        return tuple(sorted(self._items))

    def usage(self, resource: str) -> tuple[Reservation, ...]:
        return tuple(r for r in self.items() if r.resource == resource)

    def utilization(self, resource: str, start: float, end: float) -> float:
        if end <= start:
            raise ValueError('end must be after start')
        busy = 0.0
        for item in self.usage(resource):
            busy += max(0.0, min(item.end, end) - max(item.start, start))
        return busy / (end - start)

    def free_windows(self, resource: str, start: float, end: float) -> list[tuple[float, float]]:
        windows: list[tuple[float, float]] = []
        cursor = start
        for item in sorted(self.usage(resource), key=lambda r: r.start):
            if item.end <= start or item.start >= end:
                continue
            if item.start > cursor:
                windows.append((cursor, min(item.start, end)))
            cursor = max(cursor, item.end)
        if cursor < end:
            windows.append((cursor, end))
        return windows

    # -- deadlock --------------------------------------------------------------
    def wait_for(self, waiter: str, holder: str) -> None:
        self._waiting.setdefault(waiter, set()).add(holder)

    def clear_wait(self, waiter: str) -> None:
        self._waiting.pop(waiter, None)

    def wait_graph(self) -> dict[str, set[str]]:
        live = {r.holder for r in self._items}
        return {waiter: {h for h in holders if h in live}
                for waiter, holders in self._waiting.items() if holders}

    def detect_deadlock(self) -> list[str] | None:
        """Return one cycle (``['a', 'b', 'a']``) or ``None`` when acyclic."""
        graph = self.wait_graph()
        visiting: set[str] = set()
        done: set[str] = set()
        stack: list[str] = []

        def walk(node: str) -> list[str] | None:
            if node in done:
                return None
            if node in visiting:
                return stack[stack.index(node):] + [node]
            visiting.add(node)
            stack.append(node)
            for nxt in sorted(graph.get(node, ())):
                cycle = walk(nxt)
                if cycle:
                    return cycle
            stack.pop()
            visiting.discard(node)
            done.add(node)
            return None

        for node in sorted(graph):
            cycle = walk(node)
            if cycle:
                return cycle
        return None

    def require_no_deadlock(self) -> None:
        cycle = self.detect_deadlock()
        if cycle:
            raise Deadlock(cycle)

    def _conflicting(self, left: Reservation, right: Reservation) -> bool:
        if left.resource != right.resource or left.holder == right.holder:
            return False
        return left.overlaps(right)
