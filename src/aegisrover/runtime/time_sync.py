from dataclasses import dataclass

@dataclass
class ClockModel:
    offset: float = 0.0
    drift: float = 0.0
    reference_remote: float = 0.0

    def remote_to_local(self, t):
        dt = t - self.reference_remote
        return t + self.offset + self.drift * dt

def estimate(pairs):
    pts = list(pairs)
    if len(pts) < 2:
        raise ValueError('need pairs')
    xs = [p[0] for p in pts]
    ys = [p[1] - p[0] for p in pts]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denom = sum(((x - mx) ** 2 for x in xs))
    drift = 0.0 if denom == 0 else sum(((x - mx) * (y - my) for x, y in zip(xs, ys))) / denom
    offset = my - drift * (mx - xs[0])
    return ClockModel(offset, drift, xs[0])
