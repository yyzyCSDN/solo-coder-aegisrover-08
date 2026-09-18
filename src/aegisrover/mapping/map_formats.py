import json
import hashlib
import math

def encode_grid(grid):
    height = len(grid)
    width = len(grid[0]) if height else 0
    payload = {'width': width, 'height': height, 'cells': [v for row in grid for v in row]}
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))

def decode_grid(text):
    payload = json.loads(text)
    width = int(payload['width'])
    height = int(payload['height'])
    cells = list(payload['cells'])
    if len(cells) != width * height:
        raise ValueError('cell count')
    return [cells[y * width:(y + 1) * width] for y in range(height)]

def grid_digest(grid):
    return hashlib.sha256(encode_grid(grid).encode()).hexdigest()

def tile_key(x, y, zoom):
    if zoom < 0 or x < 0 or y < 0:
        raise ValueError('tile')
    return f'{zoom}/{x}/{y}'
