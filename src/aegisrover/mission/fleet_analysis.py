import math
from collections import defaultdict

def group_by_robot(tasks):
    out = defaultdict(list)
    for task in tasks:
        out[task['robot']].append(task)
    return dict(out)

def fleet_utilization(assignments, horizon):
    if horizon <= 0:
        raise ValueError('horizon')
    busy = defaultdict(float)
    for item in assignments:
        busy[item['robot']] += max(0.0, item['end'] - item['start'])
    return {robot: min(1.0, value / horizon) for robot, value in busy.items()}
