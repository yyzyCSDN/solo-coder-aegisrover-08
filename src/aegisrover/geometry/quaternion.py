import math

def normalize(q):
    n = math.sqrt(sum((v * v for v in q)))
    if n == 0:
        raise ValueError('zero quaternion')
    return tuple((v / n for v in q))

def multiply(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)

def conjugate(q):
    w, x, y, z = q
    return (w, -x, -y, -z)

def rotate(q, v):
    q = normalize(q)
    p = (0.0, *v)
    r = multiply(multiply(q, p), conjugate(q))
    return r[1:]

def from_yaw(yaw):
    return (math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2))

def to_yaw(q):
    w, x, y, z = normalize(q)
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
