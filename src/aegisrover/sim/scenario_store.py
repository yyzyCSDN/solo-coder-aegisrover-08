import json
import hashlib
from dataclasses import dataclass, field

@dataclass
class ScenarioRecord:
    scenario_id: str
    revision: int
    payload: dict
    digest: str

def digest_payload(payload):
    body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(body).hexdigest()

def create_record(scenario_id, revision, payload):
    return ScenarioRecord(scenario_id, int(revision), dict(payload), digest_payload(payload))

def verify_record(record):
    return record.digest == digest_payload(record.payload)

def diff_records(a, b):
    keys = set(a.payload) | set(b.payload)
    return {k: (a.payload.get(k), b.payload.get(k)) for k in sorted(keys) if a.payload.get(k) != b.payload.get(k)}
