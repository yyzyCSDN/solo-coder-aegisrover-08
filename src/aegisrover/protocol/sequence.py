def newer(a, b, bits=16):
    mod = 1 << bits
    half = mod >> 1
    d = (a - b) % mod
    return 0 < d < half

def unwrap(previous_unwrapped, current, bits=16):
    mod = 1 << bits
    base = previous_unwrapped - previous_unwrapped % mod
    cand = base + current
    options = [cand - mod, cand, cand + mod]
    return min(options, key=lambda x: abs(x - previous_unwrapped))
