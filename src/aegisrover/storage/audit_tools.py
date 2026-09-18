import hashlib
import json

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def hash_event(previous, event):
    return hashlib.sha256(previous.encode() + canonical(event).encode()).hexdigest()
