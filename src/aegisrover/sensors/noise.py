import random, math

def gaussian(values, sigma, seed=0):
    r = random.Random(seed)
    return [v + r.gauss(0, sigma) for v in values]

def dropout(values, probability, seed=0):
    r = random.Random(seed)
    return [None if r.random() < probability else v for v in values]
