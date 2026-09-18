import math

def stopping_distance(speed, deceleration):
    if deceleration <= 0:
        return float('inf')
    return speed * speed / (2 * deceleration)

def safe_speed(clearance, deceleration):
    if clearance <= 0:
        return 0.0
    return math.sqrt(2 * max(0.0, deceleration) * clearance)
