import hashlib, json

def create(name, sequence, state):
    body = json.dumps(state, sort_keys=True, separators=(',', ':')).encode()
    return {'name': name, 'sequence': sequence, 'state': state, 'digest': hashlib.sha256(body).hexdigest()}

def verify(c):
    return c['digest'] == hashlib.sha256(json.dumps(c['state'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
