import math

def clamp(value, low, high):
    if low > high:
        raise ValueError('bounds')
    return max(low, min(high, value))

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_point(a, b, t):
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))

def distance(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])

def squared_distance(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return dx * dx + dy * dy

def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]

def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]

def norm(v):
    return math.hypot(v[0], v[1])

def normalize(v):
    n = norm(v)
    if n == 0:
        raise ValueError('zero vector')
    return (v[0] / n, v[1] / n)

def project_point_to_segment(p, a, b):
    vx = b[0] - a[0]
    vy = b[1] - a[1]
    den = vx * vx + vy * vy
    if den == 0:
        return (a, 0.0)
    t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / den
    t = clamp(t, 0.0, 1.0)
    return ((a[0] + t * vx, a[1] + t * vy), t)

def polyline_length(points):
    pts = list(points)
    return sum((distance(a, b) for a, b in zip(pts, pts[1:])))

def cumulative_lengths(points):
    pts = list(points)
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + distance(a, b))
    return out

def sample_polyline(points, spacing):
    pts = list(points)
    if spacing <= 0:
        raise ValueError('spacing')
    if len(pts) < 2:
        return pts
    lengths = cumulative_lengths(pts)
    total = lengths[-1]
    targets = [i * spacing for i in range(int(total // spacing) + 1)]
    if not targets or targets[-1] < total:
        targets.append(total)
    result = []
    seg = 0
    for target in targets:
        while seg + 1 < len(lengths) and lengths[seg + 1] < target:
            seg += 1
        span = lengths[seg + 1] - lengths[seg] if seg + 1 < len(lengths) else 0
        t = 0 if span == 0 else (target - lengths[seg]) / span
        result.append(lerp_point(pts[seg], pts[min(seg + 1, len(pts) - 1)], t))
    return result

def signed_area(polygon):
    pts = list(polygon)
    if len(pts) < 3:
        return 0.0
    return 0.5 * sum((a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1])))

def is_clockwise(polygon):
    return signed_area(polygon) < 0

def bounding_box(points):
    pts = list(points)
    if not pts:
        raise ValueError('empty points')
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))

def boxes_intersect(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or (b[3] < a[1]))

def point_in_box(point, box):
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]

def orientation(a, b, c):
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(value) < 1e-12:
        return 0
    return 1 if value > 0 else -1

def segment_intersection(a, b, c, d):
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = cross(r, s)
    if abs(den) < 1e-12:
        return None
    ca = (c[0] - a[0], c[1] - a[1])
    t = cross(ca, s) / den
    u = cross(ca, r) / den
    if 0 <= t <= 1 and 0 <= u <= 1:
        return (a[0] + t * r[0], a[1] + t * r[1])
    return None

def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def turn(o, a, b):
        return cross((a[0] - o[0], a[1] - o[1]), (b[0] - o[0], b[1] - o[1]))
    lower = []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]

def rotate_point(p, angle, origin=(0.0, 0.0)):
    c = math.cos(angle)
    s = math.sin(angle)
    x = p[0] - origin[0]
    y = p[1] - origin[1]
    return (origin[0] + c * x - s * y, origin[1] + s * x + c * y)

def bezier_quadratic(p0, p1, p2, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])

def bezier_cubic(p0, p1, p2, p3, t):
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0], u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])
