import heapq

class Scheduler:

    def __init__(self):
        self.q = []
        self.seq = 0
        self.time = 0.0

    def at(self, time, callback, name=''):
        if time < self.time:
            raise ValueError('past')
        self.seq += 1
        heapq.heappush(self.q, (float(time), self.seq, name, callback))

    def run_until(self, end):
        out = []
        while self.q and self.q[0][0] <= end:
            t, seq, name, cb = heapq.heappop(self.q)
            self.time = t
            out.append((t, name, cb()))
        self.time = max(self.time, end)
        return out
