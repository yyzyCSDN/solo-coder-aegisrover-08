import hmac, hashlib, struct

def sign(secret: bytes, sequence: int, payload: bytes):
    return hmac.new(secret, struct.pack('>Q', sequence) + payload, hashlib.sha256).digest()

class ReplayWindow:

    def __init__(self, size=64):
        self.size = size
        self.high = -1
        self.bits = 0

    def accept(self, seq):
        if seq > self.high:
            shift = seq - self.high
            self.bits = 0 if shift >= self.size else self.bits << shift & (1 << self.size) - 1
            self.bits |= 1
            self.high = seq
            return True
        delta = self.high - seq
        if delta >= self.size:
            return False
        mask = 1 << delta
        if self.bits & mask:
            return False
        self.bits |= mask
        return True

def verify(secret, sequence, payload, tag, window):
    if not hmac.compare_digest(sign(secret, sequence, payload), tag):
        return False
    return window.accept(sequence)
