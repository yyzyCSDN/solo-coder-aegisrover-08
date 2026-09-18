import math
import statistics

def packet_loss_rate(sent, received):
    return 0.0 if sent <= 0 else max(0.0, min(1.0, (sent - received) / sent))

def jitter(delays):
    xs = list(map(float, delays))
    if len(xs) < 2:
        return 0.0
    diff = [abs(b - a) for a, b in zip(xs, xs[1:])]
    return sum(diff) / len(diff)
