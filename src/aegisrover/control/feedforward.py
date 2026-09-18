def wheel_speeds(linear, angular, wheel_base, radius):
    if radius <= 0:
        raise ValueError('radius')
    return ((linear - angular * wheel_base / 2) / radius, (linear + angular * wheel_base / 2) / radius)
