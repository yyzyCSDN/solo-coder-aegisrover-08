import json

def validate_keys(payload, required, allowed):
    missing = sorted(set(required) - set(payload))
    extra = sorted(set(payload) - set(allowed))
    return {'ok': not missing and (not extra), 'missing': missing, 'extra': extra}

def canonical_query(params):
    return '&'.join((f'{k}={params[k]}' for k in sorted(params)))

def parse_bool(value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'on'}:
        return True
    if text in {'0', 'false', 'no', 'off'}:
        return False
    raise ValueError('bool')

def parse_int(value, low=None, high=None):
    number = int(value)
    if low is not None and number < low:
        raise ValueError('low')
    if high is not None and number > high:
        raise ValueError('high')
    return number

def merge_patch(target, patch):
    out = dict(target)
    for key, value in patch.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_patch(out[key], value)
        else:
            out[key] = value
    return out
