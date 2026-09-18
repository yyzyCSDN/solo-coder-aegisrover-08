import math
import time

def duration(start, end):
    return max(0.0, float(end) - float(start))

def throughput(count, start, end):
    d = duration(start, end)
    return 0.0 if d == 0 else count / d

def availability(up_seconds, total_seconds):
    return 1.0 if total_seconds <= 0 else max(0.0, min(1.0, up_seconds / total_seconds))
