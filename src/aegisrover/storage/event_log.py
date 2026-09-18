from dataclasses import dataclass

@dataclass(frozen=True)
class Event:
    seq: int
    mono_ns: int
    wall_ns: int
    kind: str
    payload: dict

class EventLog:

    def __init__(self):
        self.events = []
        self.next_seq = 1

    def append(self, mono_ns, wall_ns, kind, payload):
        if self.events and mono_ns < self.events[-1].mono_ns:
            raise ValueError('monotonic time moved backwards')
        e = Event(self.next_seq, mono_ns, wall_ns, kind, dict(payload))
        self.next_seq += 1
        self.events.append(e)
        return e

    def since(self, seq):
        return [e for e in self.events if e.seq > seq]
