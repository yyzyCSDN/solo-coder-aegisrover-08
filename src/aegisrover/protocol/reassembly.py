from dataclasses import dataclass, field

@dataclass
class Assembly:
    total: int
    parts: dict = field(default_factory=dict)

    def add(self, index, data):
        if not 0 <= index < self.total:
            raise ValueError('index')
        previous = self.parts.get(index)
        if previous is not None and previous != data:
            raise ValueError('conflicting fragment')
        self.parts[index] = bytes(data)

    def complete(self):
        return len(self.parts) == self.total

    def payload(self):
        if not self.complete():
            raise ValueError('incomplete')
        return b''.join((self.parts[i] for i in range(self.total)))
