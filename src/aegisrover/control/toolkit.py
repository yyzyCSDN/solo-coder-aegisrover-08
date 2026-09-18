import math

def deadband(value, width):
    if abs(value) <= width:
        return 0.0
    return math.copysign(abs(value) - width, value)

def saturate(value, low, high):
    return max(low, min(high, value))

def rate_limit(previous, desired, rate, dt):
    delta = max(0.0, rate) * max(0.0, dt)
    return max(previous - delta, min(previous + delta, desired))

def lowpass(previous, sample, cutoff_hz, dt):
    if cutoff_hz <= 0:
        return previous
    rc = 1 / (2 * math.pi * cutoff_hz)
    alpha = dt / (rc + dt)
    return previous + alpha * (sample - previous)

def highpass(previous_output, previous_input, sample, cutoff_hz, dt):
    rc = 1 / (2 * math.pi * cutoff_hz)
    alpha = rc / (rc + dt)
    return alpha * (previous_output + sample - previous_input)

def feedforward_velocity(velocity, acceleration, ks, kv, ka):
    sign = 0 if velocity == 0 else 1 if velocity > 0 else -1
    return ks * sign + kv * velocity + ka * acceleration

def wheel_commands(linear, angular, wheel_base):
    return (linear - angular * wheel_base / 2, linear + angular * wheel_base / 2)

def curvature_command(linear, curvature, wheel_base):
    angular = linear * curvature
    return wheel_commands(linear, angular, wheel_base)
