from dataclasses import dataclass, field
import json
import hashlib

@dataclass
class VersionedValue:
    value: object
    version: int
    updated_at: float

@dataclass
class InMemoryTable:
    rows: dict = field(default_factory=dict)
    clock: int = 0

    def put(self, key, value):
        self.clock += 1
        self.rows[key] = VersionedValue(value, self.clock, float(self.clock))
        return self.clock

    def get(self, key):
        return self.rows.get(key)

    def delete(self, key):
        self.clock += 1
        return self.rows.pop(key, None)

def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def digest_json(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def etag(version, value):
    return f'{version:x}-' + digest_json(value)[:16]

def page(items, cursor, limit):
    start = 0 if cursor is None else int(cursor)
    end = min(len(items), start + limit)
    next_cursor = str(end) if end < len(items) else None
    return (items[start:end], next_cursor)

def append_hash_chain(previous_digest, event):
    body = previous_digest.encode() + canonical_json(event).encode()
    return hashlib.sha256(body).hexdigest()
