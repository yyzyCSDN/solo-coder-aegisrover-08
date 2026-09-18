"""Cost-aware graph search with an explicit budget.

The planner runs on a cost grid where some cells are expensive (rough ground, low
traction) and some are blocked. Two properties matter operationally: the search must
be deterministic (equal-cost paths must not depend on dict ordering), and it must be
stoppable — a planner that keeps expanding forever is worse than one that reports
"no path within budget" so the mission can be re-planned.
"""
from __future__ import annotations

import hashlib
import heapq
import itertools
import math
from dataclasses import dataclass, field
from typing import Callable, Iterable

__all__ = ('SearchResult', 'TerrainGrid', 'astar', 'dijkstra', 'euclidean')

Cell = tuple[int, int]


@dataclass(frozen=True)
class SearchResult:
    path: tuple[Cell, ...] | None
    cost: float
    expanded: int
    exhausted: bool
    within_budget: bool = True

    @property
    def found(self) -> bool:
        return self.path is not None

    def digest(self) -> str:
        material = '|'.join(f'{x},{y}' for x, y in self.path or ())
        return hashlib.sha256(f'{self.cost:.6f}:{material}'.encode()).hexdigest()


def euclidean(goal: Cell) -> Callable[[Cell], float]:
    def heuristic(node: Cell) -> float:
        return math.hypot(goal[0] - node[0], goal[1] - node[1])

    return heuristic


@dataclass
class TerrainGrid:
    """Grid world with blocked cells and per-cell traversal weights."""

    width: int
    height: int
    blocked: set[Cell] = field(default_factory=set)
    weights: dict[Cell, float] = field(default_factory=dict)
    allow_diagonal: bool = False

    def inside(self, cell: Cell) -> bool:
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height

    def traversable(self, cell: Cell) -> bool:
        return self.inside(cell) and cell not in self.blocked

    def neighbors(self, cell: Cell) -> Iterable[Cell]:
        moves = ((1, 0), (-1, 0), (0, 1), (0, -1))
        if self.allow_diagonal:
            moves = moves + ((1, 1), (1, -1), (-1, 1), (-1, -1))
        for dx, dy in moves:
            candidate = (cell[0] + dx, cell[1] + dy)
            if self.traversable(candidate):
                yield candidate

    def cost(self, a: Cell, b: Cell) -> float:
        distance = math.hypot(b[0] - a[0], b[1] - a[1])
        weight = max(1e-6, float(self.weights.get(b, 1.0)))
        return distance * weight

    def total_cost(self, path: Iterable[Cell]) -> float:
        items = list(path)
        return sum(self.cost(a, b) for a, b in zip(items, items[1:]))


def astar(start: Cell, goal: Cell, neighbors: Callable[[Cell], Iterable[Cell]],
          cost: Callable[[Cell, Cell], float], *, heuristic: Callable[[Cell], float] | None = None,
          budget: int | None = None) -> SearchResult:
    """A* with deterministic tie-breaking and an optional expansion budget."""
    if start == goal:
        return SearchResult((start,), 0.0, 0, True)
    h = heuristic or euclidean(goal)
    counter = itertools.count()
    best: dict[Cell, float] = {start: 0.0}
    parent: dict[Cell, Cell] = {}
    settled: set[Cell] = set()
    queue: list[tuple[float, int, Cell]] = [(h(start), next(counter), start)]
    expanded = 0
    while queue:
        _, _, node = heapq.heappop(queue)
        if node in settled:
            continue
        settled.add(node)
        expanded += 1
        if node == goal:
            return SearchResult(_reconstruct(parent, start, goal), best[goal], expanded, True)
        if budget is not None and expanded >= budget:
            return SearchResult(None, math.inf, expanded, False, within_budget=False)
        for nxt in neighbors(node):
            tentative = best[node] + cost(node, nxt)
            if tentative < best.get(nxt, math.inf) - 1e-12:
                best[nxt] = tentative
                parent[nxt] = node
                heapq.heappush(queue, (tentative + h(nxt), next(counter), nxt))
    return SearchResult(None, math.inf, expanded, True)


def dijkstra(start: Cell, goal: Cell, neighbors: Callable[[Cell], Iterable[Cell]],
             cost: Callable[[Cell, Cell], float]) -> SearchResult:
    """Reference implementation used to validate that A* really is optimal."""
    return astar(start, goal, neighbors, cost, heuristic=lambda _node: 0.0)


def _reconstruct(parent: dict[Cell, Cell], start: Cell, goal: Cell) -> tuple[Cell, ...]:
    path = [goal]
    while path[-1] != start:
        path.append(parent[path[-1]])
    return tuple(reversed(path))
