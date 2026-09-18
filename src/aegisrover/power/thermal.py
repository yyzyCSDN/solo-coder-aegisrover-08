def derating_factor(temp_c, start_c, shutdown_c):
    if shutdown_c <= start_c:
        raise ValueError('range')
    if temp_c <= start_c:
        return 1.0
    if temp_c >= shutdown_c:
        return 0.0
    return (shutdown_c - temp_c) / (shutdown_c - start_c)

def power_limit(nominal, temp_c, start_c, shutdown_c):
    return nominal * derating_factor(temp_c, start_c, shutdown_c)
