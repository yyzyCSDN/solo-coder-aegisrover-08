import struct, zlib
MAGIC = b'AR'

def encode(kind: int, payload: bytes):
    header = MAGIC + struct.pack('>BH', kind, len(payload))
    crc = zlib.crc32(header + payload) & 4294967295
    return header + payload + struct.pack('>I', crc)

def decode(data: bytes):
    if len(data) < 9 or data[:2] != MAGIC:
        raise ValueError('frame')
    kind, length = struct.unpack('>BH', data[2:5])
    expected = 5 + length + 4
    if len(data) != expected:
        raise ValueError('length')
    payload = data[5:5 + length]
    stored = struct.unpack('>I', data[-4:])[0]
    if zlib.crc32(data[:-4]) & 4294967295 != stored:
        raise ValueError('crc')
    return (kind, payload)
