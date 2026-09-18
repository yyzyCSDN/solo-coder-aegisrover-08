from dataclasses import dataclass

@dataclass
class Watchdog:
    wall_limit: float
    cpu_limit: float
    started_wall: float
    started_cpu: float

    def status(self, wall_now, cpu_now):
        wall = wall_now - self.started_wall
        cpu = cpu_now - self.started_cpu
        if wall > self.wall_limit:
            return 'wall_timeout'
        if cpu > self.cpu_limit:
            return 'cpu_timeout'
        return 'ok'
