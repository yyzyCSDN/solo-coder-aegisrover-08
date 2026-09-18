from collections import deque

class MovingAverage:

    def __init__(self, n):
        self.n = n
        self.q = deque()
        self.total = 0.0

    def push(self, x):
        self.q.append(float(x))
        self.total += x
        if len(self.q) > self.n:
            self.total -= self.q.popleft()
        return self.total / len(self.q)
