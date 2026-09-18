def orientation(a, b, c):
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 0 if abs(v) < 1e-12 else 1 if v > 0 else -1

def intersects(a, b, c, d):
    o1, o2, o3, o4 = (orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b))
    return o1 * o2 <= 0 and o3 * o4 <= 0
