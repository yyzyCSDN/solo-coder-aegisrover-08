import hashlib
import json

def request_id(method, path, body):
    payload = json.dumps(body, sort_keys=True, separators=(',', ':')) if body is not None else ''
    return hashlib.sha256(f'{method}:{path}:{payload}'.encode()).hexdigest()[:24]

def page_bounds(page, size, total):
    if page < 1 or size < 1:
        raise ValueError('pagination')
    start = (page - 1) * size
    end = min(total, start + size)
    return (start, end)

def sort_rows(rows, key, descending=False):
    return sorted(rows, key=lambda x: (x.get(key) is None, x.get(key)), reverse=descending)
