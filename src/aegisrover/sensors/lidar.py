import math

def sanitize_ranges(values, min_range, max_range):
    out = []
    for v in values:
        if v is None or not math.isfinite(v):
            out.append(None)
        elif v < min_range or v > max_range:
            out.append(None)
        else:
            out.append(float(v))
    return out

def points_from_scan(ranges, angle_min, angle_increment, min_range, max_range):
    clean = sanitize_ranges(ranges, min_range, max_range)
    pts = []
    for i, r in enumerate(clean):
        if r is None:
            continue
        a = angle_min + i * angle_increment
        pts.append((r * math.cos(a), r * math.sin(a), i))
    return pts

def nearest(ranges, min_range, max_range):
    clean = [x for x in sanitize_ranges(ranges, min_range, max_range) if x is not None]
    return min(clean) if clean else None
