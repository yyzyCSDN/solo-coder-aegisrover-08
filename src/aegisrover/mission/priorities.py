import heapq

class Queue:

    def __init__(self):
        self.q = []
        self.seq = 0

    def push(self, item, priority):
        self.seq += 1
        heapq.heappush(self.q, (-priority, self.seq, item))

    def pop(self):
        return heapq.heappop(self.q)[2] if self.q else None
