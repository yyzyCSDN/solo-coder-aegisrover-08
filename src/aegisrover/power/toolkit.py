import math

def mechanical_power(force, speed):
    return force * speed

def rolling_force(mass, coefficient=0.015):
    return mass * 9.81 * coefficient

def aero_force(speed, drag_coefficient=0.3):
    return drag_coefficient * speed * speed

def grade_force(mass, slope_radians):
    return mass * 9.81 * math.sin(slope_radians)

def drive_energy(mass, distance, speed, slope=0.0):
    force = rolling_force(mass) + aero_force(speed) + grade_force(mass, slope)
    return max(0.0, force * distance)

def range_estimate(available_wh, wh_per_meter):
    if wh_per_meter <= 0:
        return float('inf')
    return available_wh / wh_per_meter

def charging_curve(soc, max_current):
    if soc < 0.8:
        return max_current
    tail = max(0.0, (1.0 - soc) / 0.2)
    return max_current * tail

def thermal_balance(temperature, ambient, heat_w, cooling_w_per_c, dt, capacity_j_per_c):
    loss = cooling_w_per_c * (temperature - ambient)
    return temperature + (heat_w - loss) * dt / capacity_j_per_c
