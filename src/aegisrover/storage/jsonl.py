import json

def dump(rows):
    return ''.join((json.dumps(r, sort_keys=True, separators=(',', ':')) + '\n' for r in rows))

def load(text):
    return [json.loads(x) for x in text.splitlines() if x.strip()]
