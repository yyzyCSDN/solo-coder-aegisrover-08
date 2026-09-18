def delta_ticks(previous, current, bits):
    modulus = 1 << bits
    half = modulus >> 1
    raw = (current - previous) % modulus
    if raw >= half:
        raw -= modulus
    return raw

def distance_from_ticks(delta, ticks_per_rev, wheel_circumference):
    if ticks_per_rev <= 0:
        raise ValueError('ticks_per_rev')
    return delta / ticks_per_rev * wheel_circumference
