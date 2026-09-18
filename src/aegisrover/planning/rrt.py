import random, math

def extend(tree, sample, step):
    near = min(tree, key=lambda p: math.dist(p, sample))
    d = math.dist(near, sample)
    if d <= step:
        return sample
    t = step / d
    return (near[0] + (sample[0] - near[0]) * t, near[1] + (sample[1] - near[1]) * t)

def grow(start, bounds, n=100, step=1, seed=0):
    r = random.Random(seed)
    tree = [start]
    for _ in range(n):
        tree.append(extend(tree, (r.uniform(bounds[0], bounds[2]), r.uniform(bounds[1], bounds[3])), step))
    return tree
