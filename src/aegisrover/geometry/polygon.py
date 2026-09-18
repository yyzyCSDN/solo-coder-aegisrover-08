import math

def area(poly):
    return 0.5 * sum((a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1])))

def perimeter(poly):
    return sum((math.dist(a, b) for a, b in zip(poly, poly[1:] + poly[:1])))

def centroid(poly):
    a = area(poly)
    if a == 0:
        return (sum((x for x, y in poly)) / len(poly), sum((y for x, y in poly)) / len(poly))
    sx = sy = 0
    for p, q in zip(poly, poly[1:] + poly[:1]):
        c = p[0] * q[1] - q[0] * p[1]
        sx += (p[0] + q[0]) * c
        sy += (p[1] + q[1]) * c
    return (sx / (6 * a), sy / (6 * a))
