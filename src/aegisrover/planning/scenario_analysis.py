import math
import heapq

def path_signature(path):
    return tuple(((round(x, 3), round(y, 3)) for x, y in path))

def path_bbox(path):
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    return None if not path else (min(xs), min(ys), max(xs), max(ys))
