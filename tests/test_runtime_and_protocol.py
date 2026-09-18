"""Acceptance tests for the runtime and protocol domains (sessions, negotiation,
backpressure, clocks, event store and the wire transport)."""
import pytest

from aegisrover.protocol.frame import encode, decode
from aegisrover.protocol.transport import (
    FrameError, Reassembler, SequenceTracker, authenticate, decode_frame, encode_frame, verify_frame,
)
from aegisrover.protocol.auth import ReplayWindow
from aegisrover.runtime.backpressure import AdmissionController
from aegisrover.runtime.clock import MonotonicOrder, estimate as estimate_clock
from aegisrover.runtime.negotiation import (
    NegotiationError, Offer, Requirement, negotiate,
)
from aegisrover.runtime.session import ACTIVE, EXPIRED, SessionError, SessionRegistry
from aegisrover.storage.audit import AuditLog
from aegisrover.storage.event_store import EventStore
from aegisrover.storage.repository import Repository


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def tick(self, delta):
        self.now += delta
        return self.now


@pytest.fixture()
def repo():
    clock = Clock(100.0)
    repository = Repository(':memory:', clock=clock)
    yield repository
    repository.close()


# --------------------------------------------------------------------------- sessions
def test_session_lease_blocks_second_operator(repo):
    clock = Clock(100.0)
    registry = SessionRegistry(repo, audit=AuditLog(repo, clock), clock=clock)
    session = registry.open('robot-1', 'alice', lease_seconds=10, cpu_limit=5, wall_limit=60)
    assert registry.lease_holder('robot-1').session_id == session.session_id
    with pytest.raises(SessionError):
        registry.open('robot-1', 'bob', lease_seconds=10)
    clock.tick(11)
    expired = registry.expire()
    assert [s.state for s in expired] == [EXPIRED]
    replacement = registry.open('robot-1', 'bob', lease_seconds=10)
    assert replacement.operator == 'bob'


def test_session_budgets_are_independent(repo):
    clock = Clock(0.0)
    registry = SessionRegistry(repo, audit=AuditLog(repo, clock), clock=clock)
    session = registry.open('robot-2', 'carol', lease_seconds=3600, cpu_limit=5, wall_limit=30)
    clock.tick(10)
    # A job that blocks on external input burns no CPU: only the wall budget can stop it.
    still_active = registry.heartbeat(session.session_id, cpu_delta=0.0)
    assert still_active.state == ACTIVE
    clock.tick(25)
    stopped = registry.heartbeat(session.session_id, cpu_delta=0.0)
    assert stopped.state == EXPIRED
    assert any('wall' in entry.get('reason', '') for entry in stopped.audit_trail)
    assert registry.get(session.session_id).state == EXPIRED


def test_session_cpu_budget_charges_deltas(repo):
    clock = Clock(0.0)
    registry = SessionRegistry(repo, audit=AuditLog(repo, clock), clock=clock)
    session = registry.open('robot-3', 'dave', lease_seconds=3600, cpu_limit=3, wall_limit=3600)
    registry.heartbeat(session.session_id, cpu_delta=2.0)
    updated = registry.heartbeat(session.session_id, cpu_delta=2.0)
    assert updated.state == EXPIRED
    assert updated.budget.cpu_used == pytest.approx(4.0)


# ------------------------------------------------------------------------ negotiation
def test_negotiation_rejects_major_and_old_minor():
    report = negotiate(
        [Requirement('camera', major=1, minor=2, features=frozenset({'hdr'}))],
        [Offer('camera', major=2, minor=9, features=frozenset({'hdr'}))],
    )
    assert not report.ok and report.rejected[0].reason == 'major_mismatch'
    report = negotiate([Requirement('camera', major=1, minor=4)], [Offer('camera', 1, 3)])
    assert report.rejected[0].reason == 'minor_too_old'
    with pytest.raises(NegotiationError):
        report.require_ok()


def test_negotiation_degrades_optional_requirements():
    report = negotiate(
        [
            Requirement('lidar', major=1, minor=1, features=frozenset({'dense'})),
            Requirement('arm', major=1, optional=True, features=frozenset({'gripper_v2'})),
        ],
        [Offer('lidar', 1, 4, frozenset({'dense', 'range300'})), Offer('arm', 1, 1, frozenset())],
    )
    assert report.ok
    assert report.accepted['lidar'].minor == 4  # highest compatible minor wins
    assert report.degraded[0].reason == 'missing_optional_features'


# ----------------------------------------------------------------------- backpressure
def test_backpressure_checks_all_levels_before_charging():
    controller = AdmissionController(policy='reject')
    controller.add_quota('global', rate=10, burst=10)
    controller.add_quota('robot', rate=2, burst=2, parent='global')
    assert controller.admit('a', now=0, quota='robot').allowed
    assert controller.admit('b', now=0, quota='robot').allowed
    denied = controller.admit('c', now=0, quota='robot')
    assert not denied.allowed and denied.reason.startswith('quota:')
    assert controller.quota('global').bucket.tokens == pytest.approx(8.0)
    assert denied.retry_after > 0


def test_backpressure_delay_policy_and_shedding():
    controller = AdmissionController(queue_limit=2, policy='shed_lowest')
    controller.add_quota('global', rate=0.0, burst=0.0)
    first = controller.enqueue('low', now=0, priority=1)
    assert not first.allowed
    controller.add_quota('fast', rate=100, burst=100)
    assert controller.enqueue('mid', now=0, priority=5, quota='fast').allowed
    assert controller.enqueue('high', now=0, priority=9, quota='fast').allowed
    assert controller.shed == 0
    assert controller.enqueue('higher', now=0, priority=10, quota='fast').allowed
    assert controller.shed == 1  # 'mid' was the lowest priority queued request
    snapshot = controller.snapshot(now=0)
    assert snapshot['queue_depth'] == 2
    assert controller.rejected == 1  # the quota-blocked 'low' request


def test_backpressure_rejects_insufficient_priority_for_shedding():
    controller = AdmissionController(queue_limit=1, policy='shed_lowest')
    controller.add_quota('fast', rate=100, burst=100)
    assert controller.enqueue('a', now=0, priority=5, quota='fast').allowed
    denied = controller.enqueue('b', now=0, priority=1, quota='fast')
    assert not denied.allowed and denied.reason == 'queue_full'


# ------------------------------------------------------------------------------ clock
def test_clock_estimate_recovers_offset_and_drift():
    samples = [(100.0, 100.4), (110.0, 110.401), (120.0, 120.402), (130.0, 130.403)]
    model, quality = estimate_clock(samples)
    assert model.remote_to_local(200.0) == pytest.approx(200.405, abs=0.01)
    assert quality.used == 4 and quality.rms_error < 0.01
    assert quality.drift_ppm == pytest.approx(100, abs=5)


def test_clock_estimate_rejects_outlier():
    samples = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (3.0, 9.0), (4.0, 4.0)]
    model, quality = estimate_clock(samples)
    assert 3 in quality.rejected
    assert model.remote_to_local(10.0) == pytest.approx(10.0, abs=0.01)


def test_monotonic_order_survives_wall_clock_rollback():
    order = MonotonicOrder()
    order.observe(1000, 5_000_000, 'boot')
    order.observe(2000, 5_000_100, 'cmd')
    order.observe(3000, 4_999_900, 'cmd')  # NTP moved the wall clock backwards
    order.observe(3000, 5_000_300, 'ack')  # same monotonic stamp
    assert [e.kind for e in order.ordered()] == ['boot', 'cmd', 'cmd', 'ack']
    assert order.wall_rollback is True
    assert order.stats()['gaps'] == []


def test_event_store_replay_and_gaps(repo):
    store = EventStore(repo, clock=Clock(0.0))
    store.append('boot', {'mode': 'idle'}, mono_ns=1, wall_ns=1000)
    store.append('move', {'to': [1, 1]}, mono_ns=2, wall_ns=2000)
    snapshot = store.snapshot({'moves': 1}, seq=2)
    store.append('move', {'to': [2, 2]}, mono_ns=3, wall_ns=1900)  # wall went backwards
    assert store.detect_wall_rollback() == [3]
    state = store.replay(snapshot, lambda acc, event: {**acc, 'moves': acc['moves'] + 1})
    assert state == {'moves': 2}
    tampered = dict(snapshot, state={'moves': 0})
    with pytest.raises(ValueError):
        store.restore(tampered)


# -------------------------------------------------------------------------- protocol
def test_frame_roundtrip_and_header_is_covered_by_crc():
    data = encode_frame(7, b'hello', flags=1)
    frame = decode_frame(data)
    assert (frame.kind, frame.body, frame.flags) == (7, b'hello', 1)
    flipped = bytearray(data)
    flipped[3] ^= 0x01  # message type byte
    with pytest.raises(FrameError) as excinfo:
        decode_frame(bytes(flipped))
    assert excinfo.value.reason == 'crc'


def test_frame_rejects_bad_version_and_length():
    data = bytearray(encode_frame(1, b'x'))
    data[2] = 9
    with pytest.raises(FrameError) as excinfo:
        decode_frame(bytes(data))
    assert excinfo.value.reason == 'version'
    with pytest.raises(FrameError):
        decode_frame(encode_frame(1, b'x')[:-1])
    with pytest.raises(FrameError):
        encode_frame(1, b'x' * 5000)


def test_sequence_tracker_handles_wraparound():
    tracker = SequenceTracker(bits=16)
    assert tracker.observe(65534) == 'new'
    assert tracker.observe(65535) == 'new'
    assert tracker.observe(0) == 'new'      # wrapped, still newer
    assert tracker.observe(0) == 'duplicate'
    assert tracker.observe(65535) == 'stale'
    tracker2 = SequenceTracker(bits=16)
    tracker2.observe(10)
    assert tracker2.observe(13) == 'gap'
    assert tracker2.stats()['gaps'] == 1


def test_reassembler_conflict_and_duplicate_rules():
    reassembler = Reassembler(ttl=10.0)
    assert reassembler.add('m1', 0, 2, b'aa', now=0.0) is None
    assert reassembler.add('m1', 0, 2, b'aa', now=0.1) is None  # identical resend is idempotent
    with pytest.raises(Exception):
        reassembler.add('m1', 0, 2, b'zz', now=0.2)
    with pytest.raises(ValueError):
        reassembler.add('m1', 1, 3, b'bb', now=0.2)
    assert reassembler.add('m1', 1, 2, b'bb', now=0.3) == b'aabb'
    assert reassembler.stats()['completed'] == 1
    reassembler.add('m2', 0, 2, b'cc', now=1.0)
    assert reassembler.evict(now=99.0) == 1


def test_authenticated_frame_and_replay_window():
    secret = b'secret'
    window = ReplayWindow(size=32)
    data = encode_frame(3, b'goto', flags=2)
    frame = decode_frame(data)
    tag = authenticate(secret, 41, frame)
    assert verify_frame(secret, 41, data, tag, window).body == b'goto'
    with pytest.raises(FrameError) as excinfo:
        verify_frame(secret, 41, data, tag, window)
    assert excinfo.value.reason == 'replay'
    with pytest.raises(FrameError) as excinfo:
        verify_frame(secret, 42, data, tag, window)
    assert excinfo.value.reason == 'auth'


def test_legacy_frame_codec_still_works():
    data = encode(5, b'payload')
    assert decode(data) == (5, b'payload')
