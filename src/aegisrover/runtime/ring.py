class Ring:

    def __init__(self, n):
        self.data = [None] * n
        self.n = n
        self.start = 0
        self.size = 0

    def append(self, x):
        i = (self.start + self.size) % self.n
        if self.size == self.n:
            self.data[self.start] = x
            self.start = (self.start + 1) % self.n
        else:
            self.data[i] = x
            self.size += 1

    def items(self):
        return [self.data[(self.start + i) % self.n] for i in range(self.size)]
