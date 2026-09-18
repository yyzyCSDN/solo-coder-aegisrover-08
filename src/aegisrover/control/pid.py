from dataclasses import dataclass

@dataclass
class PID:
    kp: float
    ki: float
    kd: float
    minimum: float
    maximum: float
    integral: float = 0.0
    previous: float | None = None

    def step(self, error, dt):
        if dt <= 0:
            raise ValueError('dt')
        derivative = 0.0 if self.previous is None else (error - self.previous) / dt
        candidate = self.integral + error * dt
        raw = self.kp * error + self.ki * candidate + self.kd * derivative
        out = max(self.minimum, min(self.maximum, raw))
        if out == raw or (out == self.maximum and error < 0) or (out == self.minimum and error > 0):
            self.integral = candidate
        self.previous = error
        return out
