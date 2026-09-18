def limit_command(previous, desired, dt, min_value, max_value, max_slew):
    if dt < 0:
        raise ValueError('dt')
    desired = max(min_value, min(max_value, desired))
    delta = max_slew * dt
    return max(previous - delta, min(previous + delta, desired))

def limit_pair(previous, desired, dt, bounds, slew):
    return tuple((limit_command(p, d, dt, lo, hi, s) for p, d, (lo, hi), s in zip(previous, desired, bounds, slew)))
