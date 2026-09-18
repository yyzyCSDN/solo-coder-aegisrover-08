import math
import statistics

def pose_error(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    dyaw = (b[2] - a[2] + math.pi) % (2 * math.pi) - math.pi
    return (math.hypot(dx, dy), abs(dyaw))

def trajectory_rmse(reference, estimated):
    if len(reference) != len(estimated) or not reference:
        raise ValueError('trajectory')
    sq = []
    for a, b in zip(reference, estimated):
        d, _ = pose_error(a, b)
        sq.append(d * d)
    return math.sqrt(sum(sq) / len(sq))

def loop_closure_residuals(closures, poses):
    out = []
    for item in closures:
        a = poses[item['a']]
        b = poses[item['b']]
        dist, angle = pose_error(a, b)
        out.append({'a': item['a'], 'b': item['b'], 'distance': dist, 'angle': angle})
    return out
