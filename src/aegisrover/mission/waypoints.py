def advance(waypoints, index, position, tolerance):
    while index < len(waypoints) and ((waypoints[index][0] - position[0]) ** 2 + (waypoints[index][1] - position[1]) ** 2) ** 0.5 <= tolerance:
        index += 1
    return index

def remaining(waypoints, index):
    return waypoints[index:]
