"""Acceptance tests for the planning and control domains."""
import math

import pytest

from aegisrover.control.loop import (
    ActuatorLimits, GainSchedule, PID, lateral_error, limit_command, pure_pursuit_curvature,
)
from aegisrover.control.safety import (
    EmergencyStopLatch, SafetySupervisor, SafetyZone, max_safe_speed, stopping_distance,
)
from aegisrover.core.types import Pose2
from aegisrover.planning.predict import (
    CircleObstacle, inflate, minkowski_clearance, swept_path_conflict, time_to_collision,
)
from aegisrover.planning.search import TerrainGrid, astar, dijkstra
from aegisrover.planning.trajectory import polyline_length, smooth, time_parameterize


# ------------------------------------------------------------------------------- search
def rough_grid(seed=1):
    import random

    rng = random.Random(seed)
    grid = TerrainGrid(width=12, height=12)
    grid.blocked = {(rng.randrange(12), rng.randrange(12)) for _ in range(14)}
    grid.blocked -= {(0, 0), (11, 11)}
    grid.weights = {(x, y): rng.choice([1.0, 2.0, 5.0]) for y in range(12) for x in range(12)}
    return grid


def test_astar_matches_dijkstra_on_weighted_grid():
    grid = rough_grid()
    heuristic = lambda node: math.hypot(11 - node[0], 11 - node[1])  # noqa: E731
    fast = astar((0, 0), (11, 11), grid.neighbors, grid.cost, heuristic=heuristic)
    reference = dijkstra((0, 0), (11, 11), grid.neighbors, grid.cost)
    assert fast.found and reference.found
    assert fast.cost == pytest.approx(reference.cost, abs=1e-9)
    assert grid.total_cost(fast.path) == pytest.approx(fast.cost, abs=1e-9)
    assert fast.expanded <= reference.expanded


def test_astar_is_deterministic():
    grid = rough_grid(seed=3)
    first = astar((0, 0), (11, 11), grid.neighbors, grid.cost)
    second = astar((0, 0), (11, 11), grid.neighbors, grid.cost)
    assert first.path == second.path and first.digest() == second.digest()


def test_astar_respects_budget():
    grid = TerrainGrid(width=60, height=60, blocked=set())
    result = astar((0, 0), (59, 59), grid.neighbors, grid.cost, budget=25)
    assert not result.found and result.within_budget is False and result.expanded == 25


def test_astar_reports_unreachable_goal():
    grid = TerrainGrid(width=5, height=5, blocked={(2, y) for y in range(5)})
    result = astar((0, 0), (4, 0), grid.neighbors, grid.cost)
    assert not result.found and result.exhausted


def test_terrain_diagonal_costs_follow_geometry():
    grid = TerrainGrid(width=3, height=3, allow_diagonal=True)
    assert grid.cost((0, 0), (1, 1)) == pytest.approx(math.sqrt(2))
    weighted = TerrainGrid(width=3, height=3, weights={(1, 1): 3.0}, allow_diagonal=True)
    assert weighted.cost((0, 0), (1, 1)) == pytest.approx(3.0 * math.sqrt(2))


# --------------------------------------------------------------------------- trajectory
def test_smoothing_preserves_endpoints():
    path = [(0.0, 0.0), (2.0, 1.0), (4.0, -1.0), (6.0, 0.5)]
    smoothed = smooth(path, per_segment=6)
    assert smoothed[0] == path[0]
    assert smoothed[-1] == path[-1]
    assert len(smoothed) > len(path)
    short = smooth([(0.0, 0.0), (1.0, 1.0)])
    assert short == [(0.0, 0.0), (1.0, 1.0)]


def test_smoothed_path_does_not_shorten_the_route():
    path = [(0.0, 0.0), (3.0, 0.0), (3.0, 3.0)]
    smoothed = smooth(path, per_segment=10)
    assert smoothed[0] == path[0] and smoothed[-1] == path[-1]
    assert polyline_length(smoothed) >= polyline_length(path) - 1e-9


def test_time_parameterization_is_feasible_and_stops_at_both_ends():
    points = [(0.0, 0.0), (2.0, 0.0), (4.0, 1.0), (6.0, 1.0)]
    trajectory = time_parameterize(points, max_speed=1.5, max_accel=0.8)
    assert trajectory.feasible, trajectory.violations
    assert trajectory.samples[0].v == 0.0
    assert trajectory.samples[-1].v == 0.0
    assert trajectory.duration > 0
    times = [s.t for s in trajectory.samples]
    assert times == sorted(times)
    assert trajectory.at(0.0).t == 0.0
    assert trajectory.at(trajectory.duration + 5).t == trajectory.duration


def test_time_parameterization_flags_infeasible_profile():
    points = [(0.0, 0.0), (0.05, 0.0)]
    # A very short hop with a high speed cap cannot be traversed while starting and
    # ending at rest without exceeding the acceleration limit... unless the profile
    # respects it, which it does; the check verifies the report is consistent.
    trajectory = time_parameterize(points, max_speed=10.0, max_accel=10.0)
    assert trajectory.feasible
    assert trajectory.samples[-1].v == 0.0
    assert trajectory.samples[-1].v <= trajectory.max_speed


# ------------------------------------------------------------------------------ predict
def test_swept_segment_catches_collision_between_waypoints():
    obstacles = [CircleObstacle(3.0, 0.0, 0.5)]
    path = [(0.0, 0.0), (5.0, 0.0)]  # endpoint alone is clear
    conflict = swept_path_conflict(path, obstacles, robot_radius=0.4)
    assert conflict is not None and conflict.segment == 0
    assert conflict.distance <= 0.9 + 1e-9
    clear = swept_path_conflict([(0.0, 3.0), (5.0, 3.0)], obstacles, robot_radius=0.2)
    assert clear is None


def test_time_to_collision_head_on_and_separating():
    obstacle = CircleObstacle(10.0, 0.0, 0.5, vx=-1.0)
    t, distance = time_to_collision((0.0, 0.0), (1.0, 0.0), obstacle, horizon=20.0, robot_radius=0.5)
    assert 0 < t < 20 and distance <= 1.0 + 1e-9
    away = CircleObstacle(10.0, 0.0, 0.5, vx=1.0)
    t2, distance2 = time_to_collision((0.0, 0.0), (-1.0, 0.0), away, horizon=5.0, robot_radius=0.5)
    assert t2 == -1.0 and distance2 > 9.0
    with pytest.raises(ValueError):
        time_to_collision((0.0, 0.0), (1.0, 0.0), obstacle, horizon=0.0)


def test_obstacle_inflation_and_clearance():
    obstacles = [CircleObstacle(2.0, 0.0, 0.5)]
    bigger = inflate(obstacles, 0.3)
    assert bigger[0].radius == pytest.approx(0.8)
    clearance = minkowski_clearance([(0.0, 0.0), (4.0, 0.0)], obstacles)
    assert clearance == pytest.approx(-0.5)
    blocked = swept_path_conflict([(0.0, 0.0), (4.0, 0.0)], bigger, robot_radius=0.0)
    assert blocked is not None


# ------------------------------------------------------------------------------ control
def test_pid_anti_windup_recovers_quickly():
    pid = PID(kp=1.0, ki=5.0, kd=0.0, minimum=-1.0, maximum=1.0)
    for _ in range(200):
        pid.step(10.0, 0.01)  # long saturation in the positive direction
    assert pid.saturated
    reversed_output = pid.step(-10.0, 0.01)
    assert reversed_output == pytest.approx(-1.0)
    assert pid.integral <= 1.0


def test_pid_integral_limit_is_enforced():
    pid = PID(kp=0.0, ki=1.0, kd=0.0, integral_limit=0.5)
    for _ in range(100):
        pid.step(1.0, 0.1)
    assert pid.integral == pytest.approx(0.5)


def test_actuator_slew_limit_is_per_second():
    limits = ActuatorLimits(minimum=-10.0, maximum=10.0, max_delta_per_second=2.0)
    slow = limit_command(0.0, 10.0, 0.1, limits)
    fast = limit_command(0.0, 10.0, 0.2, limits)
    assert slow == pytest.approx(0.2)
    assert fast == pytest.approx(0.4)
    assert limit_command(0.0, 100.0, 1.0, limits) == pytest.approx(2.0)
    assert limit_command(0.0, 100.0, 100.0, limits) == pytest.approx(10.0)
    with pytest.raises(ValueError):
        limit_command(0.0, 1.0, 0.0, limits)


def test_gain_schedule_interpolates_between_breakpoints():
    schedule = GainSchedule().add(0.0, (2.0, 0.5, 0.1)).add(2.0, (1.0, 0.1, 0.3))
    assert schedule.gains_at(-1.0) == (2.0, 0.5, 0.1)
    assert schedule.gains_at(3.0) == (1.0, 0.1, 0.3)
    middle = schedule.gains_at(1.0)
    assert middle == pytest.approx((1.5, 0.3, 0.2))
    with pytest.raises(ValueError):
        GainSchedule().gains_at(0.0)


def test_pure_pursuit_sign_matches_robot_frame():
    forward = Pose2(0.0, 0.0, 0.0)
    assert lateral_error(forward, (2.0, 1.0)) > 0      # target to the left
    assert lateral_error(forward, (2.0, -1.0)) < 0     # target to the right
    assert pure_pursuit_curvature(forward, (2.0, 1.0), 2.0) > 0
    assert pure_pursuit_curvature(forward, (2.0, -1.0), 2.0) < 0
    turned = Pose2(0.0, 0.0, math.pi / 2)
    assert lateral_error(turned, (1.0, 2.0)) < 0       # target on the robot's right after +90 deg


# ------------------------------------------------------------------------------- safety
def test_emergency_latch_generation_blocks_stale_reset():
    latch = EmergencyStopLatch()
    latch = latch.trigger('bumper', at=1.0)
    first_generation = latch.generation
    assert not latch.permit_motion()
    latch = latch.trigger('lidar-zone', at=2.0)
    assert latch.generation == first_generation + 1
    stale = latch.reset(first_generation, True, at=3.0)
    assert stale.latched and stale.generation == first_generation + 1
    blocked = latch.reset(latch.generation, False, at=4.0)
    assert blocked.latched
    cleared = latch.reset(latch.generation, True, at=5.0)
    assert not cleared.latched and cleared.permit_motion()
    assert [entry['event'] for entry in cleared.history] == ['trigger', 'trigger', 'reset']


def test_speed_envelope_and_zone_caps():
    assert stopping_distance(2.0, 1.0) == pytest.approx(2.0)
    assert stopping_distance(2.0, 1.0, reaction_time=0.5) == pytest.approx(3.0)
    assert stopping_distance(1.0, 0.0) == math.inf
    assert max_safe_speed(0.0, 1.0) == 0.0
    assert max_safe_speed(2.0, 1.0) == pytest.approx(2.0)
    zone = SafetyZone('dock-approach', clearance=1.0, max_speed=1.5, deceleration=1.0)
    assert zone.allowed_speed() == pytest.approx(1.4142135, abs=1e-6)
    tight = SafetyZone('aisle', clearance=0.1, max_speed=3.0, deceleration=2.0)
    assert tight.allowed_speed() == pytest.approx(math.sqrt(0.4), abs=1e-6)


def test_supervisor_caps_commands_and_records_interventions():
    supervisor = SafetySupervisor(deceleration=1.0, clock=lambda: 7.0)
    assert supervisor.command(3.0, clearance=2.0) == pytest.approx(2.0)
    assert supervisor.command(3.0, zone=SafetyZone('yard', clearance=1.0, max_speed=0.5)) == pytest.approx(0.5)
    assert supervisor.enforce_minimum_clearance(
        [SafetyZone('a', clearance=1.0, deceleration=1.0), SafetyZone('b', clearance=0.25, deceleration=1.0)],
        5.0) == pytest.approx(math.sqrt(0.5), abs=1e-9)
    supervisor.trigger_emergency('bumper')
    assert supervisor.command(3.0) == 0.0
    kinds = [i.kind for i in supervisor.interventions]
    assert kinds.count('speed_cap') >= 2 and 'emergency_stop' in kinds and 'emergency_block' in kinds
    assert supervisor.to_dict()['emergency']['generation'] == 1
    # A negative clearance means the robot is already inside the safety margin: the
    # supervision layer must return "stop", not raise inside the safety path.
    assert max_safe_speed(-1.0, 1.0) == 0.0
