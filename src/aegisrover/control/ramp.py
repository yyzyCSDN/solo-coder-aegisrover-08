def ramp(values, max_delta, start=0):
    out = []
    cur = start
    for v in values:
        d = max(-max_delta, min(max_delta, v - cur))
        cur += d
        out.append(cur)
    return out
