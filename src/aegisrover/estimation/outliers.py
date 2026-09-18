import statistics

def hampel(values, k=3.0):
    if len(values) < 3:
        return [False] * len(values)
    med = statistics.median(values)
    dev = [abs(x - med) for x in values]
    mad = statistics.median(dev)
    scale = 1.4826 * mad
    return [False if scale == 0 else abs(x - med) > k * scale for x in values]
