from dataclasses import dataclass, field

@dataclass
class Mission:
    state: str = 'idle'
    history: list = field(default_factory=list)
    allowed = {'idle': {'start': 'running'}, 'running': {'pause': 'paused', 'complete': 'completed', 'fail': 'failed', 'cancel': 'cancelled'}, 'paused': {'resume': 'running', 'cancel': 'cancelled'}, 'failed': {}, 'completed': {}, 'cancelled': {}}

    def apply(self, event):
        nxt = self.allowed.get(self.state, {}).get(event)
        if nxt is None:
            raise ValueError(f'invalid transition {self.state}:{event}')
        old = self.state
        self.state = nxt
        self.history.append((old, event, nxt))
        return nxt
