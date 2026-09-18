def encode(n):
    if n < 0:
        raise ValueError('n')
    out = bytearray()
    while True:
        b = n & 127
        n >>= 7
        out.append(b | (128 if n else 0))
        if not n:
            return bytes(out)

def decode(data):
    n = shift = 0
    for i, b in enumerate(data):
        n |= (b & 127) << shift
        if not b & 128:
            return (n, i + 1)
        shift += 7
        if shift > 63:
            raise ValueError('overflow')
    raise ValueError('incomplete')
