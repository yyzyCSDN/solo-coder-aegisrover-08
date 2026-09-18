from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from aegisrover.service.schemas import *
from aegisrover.service.platform import PlatformService, ServiceError
from aegisrover.storage.repository import Repository
from aegisrover.planning.astar import astar
from aegisrover.control.pid import PID
from aegisrover.protocol.frame import encode, decode
from aegisrover.sim.world import World, Robot
from aegisrover.core.types import Pose2, Twist2
import base64
app = FastAPI(title='AegisRover')
service = PlatformService(Repository(':memory:'))


class MissionRequest(BaseModel):
    mission_id: str
    waypoints: list[tuple[float, float]] = Field(min_length=1)
    priority: int = 0
    required_capabilities: list[str] = Field(default_factory=list)


class CommandRequest(BaseModel):
    command: str
    assignee: str | None = None
    expected_revision: int | None = None


class SessionRequest(BaseModel):
    robot: str
    operator: str
    lease_seconds: float = 30.0


class MapRequest(BaseModel):
    cells: dict[str, int]
    if_match: int | None = None

@app.get('/live')
def live():
    return {'status': 'live'}

@app.get('/ready')
def ready():
    return {'status': 'ready'}

@app.post('/v1/plan')
def plan(req: PlanRequest):
    blocked = set(map(tuple, req.blocked))

    def neigh(n):
        x, y = n
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + d[0], y + d[1])
            if 0 <= q[0] < req.width and 0 <= q[1] < req.height and (q not in blocked):
                yield q
    path, cost = astar(tuple(req.start), tuple(req.goal), neigh, lambda a, b: 1)
    if path is None:
        raise HTTPException(409, 'unreachable')
    return {'path': path, 'cost': cost}

@app.post('/v1/pid')
def pid(req: PIDRequest):
    p = PID(req.kp, req.ki, req.kd, req.minimum, req.maximum)
    return {'outputs': [p.step(e, req.dt) for e in req.errors]}

@app.post('/v1/frame')
def frame(req: EncodeRequest):
    data = encode(req.kind, req.payload.encode())
    k, p = decode(data)
    return {'frame': base64.b64encode(data).decode(), 'decoded': {'kind': k, 'payload': p.decode()}}

@app.post('/v1/sim')
def sim(req: SimRequest):
    w = World()
    r = Robot('r', Pose2(0, 0, 0), Twist2(req.linear, req.angular))
    w.add(r)
    track = []
    for _ in range(req.steps):
        track.append(w.step(req.dt)['r'])
    return {'time': w.time, 'pose': track[-1].__dict__, 'samples': len(track)}


def _guard(operation):
    try:
        return operation()
    except ServiceError as exc:
        raise HTTPException(exc.status, detail=exc.to_dict()['error']) from None


@app.post('/v1/missions')
def create_mission(req: MissionRequest, idempotency_key: str | None = None):
    return _guard(lambda: service.create_mission(
        req.mission_id, req.waypoints, priority=req.priority,
        required_capabilities=req.required_capabilities, idempotency_key=idempotency_key))


@app.post('/v1/missions/{mission_id}/commands')
def command_mission(mission_id: str, req: CommandRequest, idempotency_key: str | None = None):
    return _guard(lambda: service.command_mission(
        mission_id, req.command, expected_revision=req.expected_revision,
        assignee=req.assignee, idempotency_key=idempotency_key))


@app.get('/v1/missions/{mission_id}')
def get_mission(mission_id: str):
    return _guard(lambda: service.get_mission(mission_id))


@app.post('/v1/sessions')
def open_session(req: SessionRequest):
    return _guard(lambda: service.open_session(req.robot, req.operator, lease_seconds=req.lease_seconds))


@app.post('/v1/maps/{map_id}')
def save_map(map_id: str, req: MapRequest):
    return _guard(lambda: service.save_map(map_id, req.cells, if_match=req.if_match))


@app.get('/v1/maps/{map_id}')
def get_map(map_id: str, revision: int | None = None):
    return _guard(lambda: service.get_map(map_id, revision))


@app.get('/v1/health')
def health():
    return service.health()


@app.get('/v1/audit')
def audit(after_seq: int = 0):
    return service.audit_export(after_seq=after_seq)
