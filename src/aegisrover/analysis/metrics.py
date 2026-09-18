from dataclasses import dataclass, field
import statistics, time

@dataclass
class MetricSeries:
    name: str
    values: list = field(default_factory=list)

    def observe(self, value):
        self.values.append(float(value))

    def summary(self):
        if not self.values:
            return {'count': 0}
        xs = sorted(self.values)
        q = lambda p: xs[min(len(xs) - 1, int((len(xs) - 1) * p))]
        return {'count': len(xs), 'min': xs[0], 'max': xs[-1], 'mean': statistics.fmean(xs), 'p50': q(0.5), 'p95': q(0.95), 'p99': q(0.99)}

class Registry:

    def __init__(self):
        self.series = {}

    def observe(self, name, value):
        self.series.setdefault(name, MetricSeries(name)).observe(value)

    def snapshot(self):
        return {k: v.summary() for k, v in self.series.items()}
