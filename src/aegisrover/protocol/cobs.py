def encode(data):
    out = bytearray()
    code_index = 0
    out.append(0)
    code = 1
    for b in data:
        if b == 0:
            out[code_index] = code
            code_index = len(out)
            out.append(0)
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 255:
                out[code_index] = code
                code_index = len(out)
                out.append(0)
                code = 1
    out[code_index] = code
    out.append(0)
    return bytes(out)

def decode(data):
    if not data or data[-1] != 0:
        raise ValueError('delimiter')
    data = data[:-1]
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        i += 1
        if code == 0 or i + code - 1 > len(data):
            raise ValueError('code')
        out.extend(data[i:i + code - 1])
        i += code - 1
        if code < 255 and i < len(data):
            out.append(0)
    return bytes(out)
