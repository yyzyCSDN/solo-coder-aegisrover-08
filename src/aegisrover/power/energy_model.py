def estimate(distance, speed, mass, rolling=0.015, drag=0.3):
    rolling_e = mass * 9.81 * rolling * distance
    drag_e = drag * speed * speed * distance
    return rolling_e + drag_e

def joules_to_wh(j):
    return j / 3600
