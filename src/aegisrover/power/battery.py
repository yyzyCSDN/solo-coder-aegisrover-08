from dataclasses import dataclass

@dataclass
class Battery:
    capacity_ah: float
    soc: float = 1.0
    coulombic_efficiency: float = 0.99

    def integrate(self, current_a, dt_seconds):
        ah = current_a * dt_seconds / 3600.0
        if ah >= 0:
            self.soc -= ah / self.capacity_ah
        else:
            self.soc -= ah * self.coulombic_efficiency / self.capacity_ah
        self.soc = max(0.0, min(1.0, self.soc))
        return self.soc

    def remaining_ah(self):
        return self.soc * self.capacity_ah
