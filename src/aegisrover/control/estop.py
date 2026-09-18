from dataclasses import dataclass

@dataclass
class EmergencyStop:
    latched: bool = False
    reason: str | None = None
    generation: int = 0

    def trigger(self, reason):
        self.latched = True
        self.reason = reason
        self.generation += 1

    def reset(self, token_generation, conditions_clear):
        if token_generation != self.generation:
            return False
        if not conditions_clear:
            return False
        self.latched = False
        self.reason = None
        return True

    def permit_motion(self):
        return not self.latched
