def aggregate(checks):
    items = [f() for f in checks]
    status = 'ok' if all((x.get('ok') for x in items)) else 'degraded'
    return {'status': status, 'checks': items}

def require(data, *keys):
    return {'ok': all((k in data for k in keys)), 'missing': [k for k in keys if k not in data]}
