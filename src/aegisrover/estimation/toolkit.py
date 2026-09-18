import math
import numpy as np

def mean(values):
    xs = list(map(float, values))
    return sum(xs) / len(xs) if xs else 0.0

def variance(values):
    xs = list(map(float, values))
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return sum(((x - m) ** 2 for x in xs)) / (len(xs) - 1)

def covariance(a, b):
    x = list(map(float, a))
    y = list(map(float, b))
    if len(x) != len(y) or len(x) < 2:
        raise ValueError('samples')
    mx, my = (mean(x), mean(y))
    return sum(((u - mx) * (v - my) for u, v in zip(x, y))) / (len(x) - 1)

def linear_regression(x, y):
    x = list(map(float, x))
    y = list(map(float, y))
    sxx = covariance(x, x)
    if sxx == 0:
        raise ValueError('singular')
    slope = covariance(x, y) / sxx
    intercept = mean(y) - slope * mean(x)
    return (slope, intercept)

def ema(values, alpha):
    if not 0 < alpha <= 1:
        raise ValueError('alpha')
    out = []
    state = None
    for value in values:
        state = float(value) if state is None else alpha * value + (1 - alpha) * state
        out.append(state)
    return out

def innovation(measurement, prediction):
    return [a - b for a, b in zip(measurement, prediction)]

def mahalanobis_squared(innovation_vector, covariance_inverse):
    v = np.asarray(innovation_vector, float)
    m = np.asarray(covariance_inverse, float)
    return float(v.T @ m @ v)

def gate(innovation_vector, covariance_inverse, threshold):
    return mahalanobis_squared(innovation_vector, covariance_inverse) <= threshold

def weighted_mean(values, weights):
    if len(values) != len(weights):
        raise ValueError('length')
    total = sum(weights)
    if total <= 0:
        raise ValueError('weights')
    return sum((v * w for v, w in zip(values, weights))) / total
