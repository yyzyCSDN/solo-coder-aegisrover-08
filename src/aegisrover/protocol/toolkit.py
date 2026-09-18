import struct

def pack_u16(value):
    if not 0 <= value <= 65535:
        raise ValueError('u16')
    return struct.pack('>H', value)

def unpack_u16(data):
    if len(data) != 2:
        raise ValueError('length')
    return struct.unpack('>H', data)[0]

def crc16(data):
    crc = 65535
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1 ^ 4129) & 65535 if crc & 32768 else crc << 1 & 65535
    return crc

def encode_tlv(kind, value):
    if not 0 <= kind <= 255 or len(value) > 65535:
        raise ValueError('tlv')
    return bytes([kind]) + pack_u16(len(value)) + bytes(value)

def decode_tlvs(data):
    out = []
    i = 0
    while i < len(data):
        if i + 3 > len(data):
            raise ValueError('header')
        kind = data[i]
        size = unpack_u16(data[i + 1:i + 3])
        i += 3
        if i + size > len(data):
            raise ValueError('value')
        out.append((kind, data[i:i + size]))
        i += size
    return out

def fragment(payload, mtu):
    if mtu <= 0:
        raise ValueError('mtu')
    return [payload[i:i + mtu] for i in range(0, len(payload), mtu)]

def join_fragments(parts):
    return b''.join(parts)

def sliding_ack(received, base, width):
    mask = 0
    for sequence in received:
        delta = sequence - base
        if 0 <= delta < width:
            mask |= 1 << delta
    return mask
