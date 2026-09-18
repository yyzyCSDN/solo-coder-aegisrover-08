"""Acceptance tests for the estimation, sensing, mission-execution, power and service domains."""
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from aegisrover.core.types import Pose2
from aegisrover.estimation.filters import KalmanFilter, mahalanobis_squared
from aegisrover.mission.execution import ExecutionError, Geofence, MissionExecution, WaypointRunner
from aegisrover.power.charging import ChargingError, ChargingSession, DockAlignment, docking_error, is_aligned
from aegisrover.power.energy import BatteryPack, DeratingCurve, budget, thermal_factor
from aegisrover.sensors.fusion import Measurement, fit_calibration, fuse, align_series
from aegisrover.service.platform import PlatformService, ServiceError
from aegisrover.storage.repository import Repository


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        self.now += 0.5
        return self.now


@pytest.fixture()
def repo():
    repository = Repository(':memory:', clock=Clock())
    yield repository
    repository.close()


# ------------------------------------------------------------------------------- filters
def test_kalman_gating_rejects_implausible_measurement():
    kf = KalmanFilter([0.0, 0.0], np.diag([0.1, 0.1]), gate=9.0)
    H = np.array([[1.0, 0.0], [0.0, 1.0]])
    R = np.diag([0.05, 0.05])
    accepted = kf.update([0.1, -0.1], H, R)
    assert accepted.accepted
    rejected = kf.update([50.0, 50.0], H, R)
    assert not rejected.accepted and rejected.reason == 'gated'
    assert kf.x[0] < 1.0
    assert kf.consistency().rejected == 1


def test_kalman_covariance_stays_healthy_over_many_steps():
    kf = KalmanFilter([0.0], np.array([[1.0]]))
    F = np.array([[1.0]])
    Q = np.array([[0.01]])
    for i in range(500):
        kf.predict(F, Q)
        kf.update([math.sin(i / 10.0)], np.array([[1.0]]), np.array([[0.05]]))
    assert kf.covariance_is_healthy()
    assert np.allclose(kf.P, kf.P.T)
    assert np.linalg.eigvalsh(kf.P).min() >= -1e-9
    report = kf.consistency()
    assert report.steps == 500 and report.consistent
    assert mahalanobis_squared([0.0], np.array([[1.0]])) == 0.0


# ------------------------------------------------------------------------------- fusion
def test_calibration_fit_reports_residuals_and_rejects_outliers():
    raw = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    truth = [0.1, 2.1, 4.1, 6.1, 8.1, 40.0]  # last point is wrong
    calibration = fit_calibration(raw, truth)
    assert calibration.scale == pytest.approx(2.0, abs=0.01)
    assert calibration.offset == pytest.approx(0.1, abs=0.01)
    assert 5 in calibration.rejected
    assert calibration.apply(1.0) == pytest.approx(2.1, abs=0.02)
    with pytest.raises(Exception):
        fit_calibration(raw, truth, tolerance=1e-6, reject_outliers=False)
    with pytest.raises(Exception):
        fit_calibration([1.0], [1.0])


def test_align_series_interpolates_and_reports_gaps():
    times = [0.0, 1.0, 3.0]
    values = [0.0, 10.0, 30.0]
    assert align_series(times, values, [0.5, 2.0]) == pytest.approx([5.0, 20.0])
    assert align_series(times, values, [-1.0, 4.0]) == [None, None]
    assert align_series(times, values, [-1.0, 4.0], extrapolate=True) == [0.0, 30.0]
    with pytest.raises(ValueError):
        align_series([0.0], [1.0], [0.5])


def test_fusion_weights_by_variance_and_freshness():
    equal_variance = [
        Measurement('lidar', 10.0, variance=0.1, age=0.0),
        Measurement('gps', 20.0, variance=0.1, age=10.0),
    ]
    fresh = fuse(equal_variance, half_life=1.0)
    assert fresh.value < 11.0
    assert fresh.weights['lidar'] > fresh.weights['gps'] * 100
    mixed_variance = [
        Measurement('lidar', 10.0, variance=0.1, age=0.0),
        Measurement('wheel', 10.5, variance=1.0, age=0.0),
    ]
    weighted = fuse(mixed_variance)
    assert weighted.weights['lidar'] > weighted.weights['wheel']
    assert weighted.value == pytest.approx(10.045, abs=0.02)
    result = fuse(equal_variance, max_age=5.0)
    assert result.stale == ('gps',)
    assert result.value == pytest.approx(10.0)
    with pytest.raises(ValueError):
        fuse([Measurement('gps', 1.0, 1.0, age=99.0)], max_age=1.0)
    with pytest.raises(ValueError):
        Measurement('x', 1.0, variance=0.0)


def test_fusion_reports_disagreement_and_drops_outlier():
    agreeing = fuse([Measurement('a', 5.0, 0.1), Measurement('b', 5.1, 0.1)])
    assert agreeing.agreement > 0.9
    disagreeing = fuse([Measurement('a', 5.0, 0.1), Measurement('b', 25.0, 0.1)])
    assert disagreeing.agreement < 0.5
    three = fuse([Measurement('a', 5.0, 0.1), Measurement('b', 5.1, 0.1), Measurement('c', 90.0, 0.1)])
    assert 'c' in three.rejected


# ---------------------------------------------------------------------------- geofence
L_SHAPE = ((0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (4.0, 4.0), (4.0, 10.0), (0.0, 10.0))


def test_geofence_handles_concave_notch():
    fence = Geofence(L_SHAPE)
    assert fence.contains((1.0, 1.0))
    assert fence.contains((9.0, 3.0))
    assert not fence.contains((6.0, 6.0))  # inside the bounding box, outside the L
    assert not fence.segment_inside((3.0, 3.0), (6.0, 6.0))
    violations = fence.violations([(1.0, 1.0), (3.0, 3.0), (6.0, 6.0)])
    assert len(violations) == 1 and violations[0][0] == 1


def test_geofence_margin_and_validation():
    fence = Geofence(L_SHAPE, margin=0.5)
    assert fence.contains((-0.25, 1.0))
    with pytest.raises(ExecutionError):
        Geofence(((0.0, 0.0), (1.0, 1.0)))
    with pytest.raises(ExecutionError):
        Geofence(L_SHAPE, margin=-1.0)


def test_waypoint_runner_advances_and_records_skips():
    runner = WaypointRunner([(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)], tolerance=0.5)
    assert runner.advance((0.1, 0.0)) == 1  # first waypoint consumed
    assert runner.advance((4.0, 0.0)) == 1  # not yet at the second
    assert runner.advance((5.05, 5.0)) == 3
    assert runner.done and len(runner.skipped) == 1  # the middle waypoint was skipped
    assert runner.progress() == 1.0
    assert runner.remaining_distance((0.0, 0.0)) == 0.0


def test_mission_execution_guards_completion_and_geofence():
    fence = Geofence(L_SHAPE)
    runner = WaypointRunner([(2.0, 2.0), (8.0, 2.0)], tolerance=0.4)
    execution = MissionExecution('m1', runner, fence)
    with pytest.raises(ExecutionError):
        execution.complete()
    assert execution.start((1.0, 1.0)) == 'running'
    with pytest.raises(ExecutionError):
        execution.start((1.0, 1.0))
    execution.tick((2.0, 2.0))
    assert execution.complete.__self__.runner.index == 1
    with pytest.raises(ExecutionError):
        execution.complete()
    execution.tick((8.0, 2.0))
    assert execution.state == 'completed'
    assert execution.summary()['progress'] == 1.0
    outside = MissionExecution('m2', WaypointRunner([(2.0, 2.0)]), fence)
    outside.start((1.0, 1.0))
    outside.tick((6.0, 6.0))
    assert outside.state == 'aborted' and 'geofence' in outside.abort_reason
    with pytest.raises(ExecutionError):
        MissionExecution('m3', WaypointRunner([(1.0, 1.0)]), fence).start((20.0, 20.0))


# ------------------------------------------------------------------------------- power
def test_battery_integration_is_period_independent():
    one_shot = BatteryPack(capacity_ah=10.0, soc=0.8)
    stepped = BatteryPack(capacity_ah=10.0, soc=0.8)
    one_shot.integrate(5.0, 1800.0)
    for _ in range(1800):
        stepped.integrate(5.0, 1.0)
    assert one_shot.soc == pytest.approx(stepped.soc, abs=1e-9)
    assert one_shot.energy_used_wh == pytest.approx(stepped.energy_used_wh, abs=1e-6)
    charge = BatteryPack(capacity_ah=10.0, soc=0.5)
    charge.integrate(-5.0, 3600.0)
    assert charge.soc == pytest.approx(0.5 + 5.0 * 0.99 / 10.0)
    assert charge.runtime_seconds(5.0) > 0
    assert charge.runtime_seconds(0.0) == math.inf
    assert charge.distance_remaining(consumption_wh_per_m=2.0) > 0


def test_thermal_derating_is_monotone_and_capped():
    assert thermal_factor(20.0, 40.0, 70.0) == 1.0
    assert thermal_factor(55.0, 40.0, 70.0) == pytest.approx(0.5)
    assert thermal_factor(80.0, 40.0, 70.0) == 0.0
    curve = DeratingCurve(start_c=40.0, shutdown_c=70.0, nominal=1000.0,
                          extra_caps=((60.0, 200.0),))
    assert curve.is_monotone()
    assert curve.limit(65.0) <= curve.limit(55.0) <= curve.limit(30.0)
    assert curve.limit(65.0) == pytest.approx(1000.0 * thermal_factor(65.0, 40.0, 70.0))
    assert curve.limit(60.0) == pytest.approx(200.0)  # the cap binds once thermal allows more
    assert budget(1000.0, 20.0, curve).binding_constraint == 'none'
    assert budget(1000.0, 55.0, curve).binding_constraint == 'thermal'
    assert budget(1000.0, 60.0, curve).binding_constraint == 'cap'
    with pytest.raises(ValueError):
        thermal_factor(50.0, 70.0, 40.0)


def test_docking_frame_is_dock_relative():
    dock = Pose2(10.0, 10.0, math.pi / 2)
    approaching = Pose2(10.0, 12.0, math.pi / 2)  # two metres out along the dock's approach axis
    forward, left, heading = docking_error(approaching, dock)
    assert forward == pytest.approx(2.0, abs=1e-9)
    assert left == pytest.approx(0.0, abs=1e-9)
    assert heading == pytest.approx(0.0, abs=1e-9)
    assert not is_aligned(approaching, dock)
    parked = Pose2(10.0, 10.0, math.pi / 2)
    assert is_aligned(parked, dock, DockAlignment(0.01, 0.01, 0.01))
    sideways = Pose2(10.2, 12.0, math.pi / 2)  # lateral offset in the dock frame
    assert docking_error(sideways, dock)[1] == pytest.approx(-0.2, abs=1e-9)
    assert docking_error(parked, dock) == pytest.approx((0.0, 0.0, 0.0))


def test_charging_session_flow_and_drift_abort():
    battery = BatteryPack(capacity_ah=4.0, soc=0.5)
    dock = Pose2(0.0, 0.0, 0.0)
    session = ChargingSession('s1', dock, battery, alignment=DockAlignment(0.05, 0.05, 0.05))
    with pytest.raises(ChargingError):
        session.start_charge(10.0)
    assert session.observe(Pose2(1.0, 0.0, 0.0)) == 'approach'
    assert session.observe(Pose2(0.02, 0.01, 0.01)) == 'contact'
    session.start_charge(10.0)
    assert session.state == 'charging'
    session.step(10.0, 600.0)
    assert battery.soc > 0.5
    assert session.charged_ah > 0
    session.observe(Pose2(0.02, 0.5, 0.01))  # drifted far to the side
    assert session.state == 'aborted'
    assert session.realign() == 'approach'
    assert session.summary()['events'][0] == 'contact'


# ------------------------------------------------------------------------------ service
def test_service_idempotency_and_error_contract(repo):
    service = PlatformService(repo, clock=Clock())
    first = service.create_mission('m1', [(0, 0), (5, 0)], idempotency_key='abc')
    again = service.create_mission('m1', [(0, 0), (5, 0)], idempotency_key='abc')
    assert again.get('idempotent') is True
    assert again['mission']['revision'] == first['mission']['revision']
    assert len(service.list_missions()) == 1
    with pytest.raises(ServiceError) as excinfo:
        service.get_mission('missing')
    assert excinfo.value.status == 404 and excinfo.value.code == 'mission_not_found'
    service.command_mission('m1', 'queue', idempotency_key='q1')
    with pytest.raises(ServiceError) as excinfo:
        service.command_mission('m1', 'complete', idempotency_key='c1')
    assert excinfo.value.status == 409 and excinfo.value.code == 'invalid_transition'
    with pytest.raises(ServiceError) as excinfo:
        service.command_mission('m1', 'assign', expected_revision=99, assignee='r1', idempotency_key='a1')
    assert excinfo.value.code == 'revision_conflict'


def test_service_map_etags_sessions_and_health(repo):
    service = PlatformService(repo, clock=Clock())
    saved = service.save_map('yard', {(0, 0): 1})
    assert saved['revision'] == 1 and saved['etag']
    with pytest.raises(ServiceError) as excinfo:
        service.save_map('yard', {(0, 0): 2}, if_match=0)
    assert excinfo.value.code == 'revision_conflict'
    fetched = service.get_map('yard')
    assert fetched['etag'] == saved['etag'] and fetched['cells'] == {'0,0': 1}
    service.open_session('robot-1', 'alice', lease_seconds=5, cpu_limit=5, wall_limit=60)
    with pytest.raises(ServiceError) as excinfo:
        service.open_session('robot-1', 'bob', lease_seconds=5)
    assert excinfo.value.code == 'session_conflict'
    health = service.health()
    assert health['status'] == 'ok' and health['checks']['audit_chain']['ok'] is True
    export = service.audit_export()
    assert export['entries'] and export['breaks'] == []


def test_platform_api_endpoints():
    from aegisrover.service.api import app, service as api_service

    client = TestClient(app)
    created = client.post('/v1/missions', json={'mission_id': 'api-m1', 'waypoints': [[0, 0], [1, 1]]})
    assert created.status_code == 200
    queued = client.post('/v1/missions/api-m1/commands', json={'command': 'queue'})
    assert queued.status_code == 200 and queued.json()['applied'] is True
    repeated = client.post('/v1/missions/api-m1/commands', json={'command': 'complete'})
    assert repeated.status_code == 409
    assert client.get('/v1/missions/api-m1').status_code == 200
    assert client.get('/v1/health').json()['status'] in ('ok', 'degraded')
    assert client.get('/v1/maps/nope').status_code == 404
    assert client.get('/live').json() == {'status': 'live'}
