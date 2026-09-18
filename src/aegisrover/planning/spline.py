def catmull_rom(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t

    def one(a, b, c, d):
        return 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)
    return (one(p0[0], p1[0], p2[0], p3[0]), one(p0[1], p1[1], p2[1], p3[1]))

def sample(points, per_segment=8):
    if len(points) < 2:
        return list(points)
    ext = [points[0], *points, points[-1]]
    out = []
    for i in range(1, len(ext) - 2):
        for k in range(per_segment):
            out.append(catmull_rom(ext[i - 1], ext[i], ext[i + 1], ext[i + 2], k / per_segment))
    out.append(points[-1])
    return out
