import json, hashlib

def encode_snapshot(state, sequence):
    body = json.dumps({'sequence': sequence, 'state': state}, sort_keys=True, separators=(',', ':')).encode()
    digest = hashlib.sha256(body).hexdigest()
    return json.dumps({'body': body.decode(), 'sha256': digest}, sort_keys=True).encode()

def decode_snapshot(data):
    outer = json.loads(data)
    body = outer['body'].encode()
    if hashlib.sha256(body).hexdigest() != outer['sha256']:
        raise ValueError('snapshot checksum')
    inner = json.loads(body)
    return (inner['state'], inner['sequence'])

def replay(snapshot_state, snapshot_seq, events, apply):
    state = snapshot_state
    for event in events:
        if event.seq > snapshot_seq:
            state = apply(state, event)
    return state
