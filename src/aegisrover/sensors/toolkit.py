import math
import statistics

def linear_calibration(raw, scale, offset):
    return raw * scale + offset

def quadratic_calibration(raw, a, b, c):
    return a * raw * raw + b * raw + c

def clip(value, low, high):
    return max(low, min(high, value))

def median3(a, b, c):
    return sorted((a, b, c))[1]

def moving_median(values, window):
    if window <= 0:
        raise ValueError('window')
    out = []
    for i in range(len(values)):
        chunk = sorted(values[max(0, i - window + 1):i + 1])
        out.append(chunk[len(chunk) // 2])
    return out

def linear_interpolate(t0, v0, t1, v1, t):
    if t1 == t0:
        return v1
    f = (t - t0) / (t1 - t0)
    return v0 + f * (v1 - v0)

def align_series(times, values, targets):
    if len(times) != len(values):
        raise ValueError('length')
    out = []
    j = 0
    for target in targets:
        while j + 1 < len(times) and times[j + 1] < target:
            j += 1
        if j + 1 >= len(times):
            out.append(values[-1])
        else:
            out.append(linear_interpolate(times[j], values[j], times[j + 1], values[j + 1], target))
    return out

def decimate(values, factor):
    if factor <= 0:
        raise ValueError('factor')
    return list(values)[::factor]

def saturations(values, low, high):
    return [i for i, value in enumerate(values) if value <= low or value >= high]

def dropout_runs(values):
    runs = []
    start = None
    for i, value in enumerate(values):
        if value is None and start is None:
            start = i
        if value is not None and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(values)))
    return runs
