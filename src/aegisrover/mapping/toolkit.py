import math

def neighbors4(x, y, width, height):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = (x + dx, y + dy)
        if 0 <= nx < width and 0 <= ny < height:
            yield (nx, ny)

def neighbors8(x, y, width, height):
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = (x + dx, y + dy)
            if 0 <= nx < width and 0 <= ny < height:
                yield (nx, ny)

def flood_fill(grid, start, predicate):
    height = len(grid)
    width = len(grid[0]) if height else 0
    if not (0 <= start[0] < width and 0 <= start[1] < height):
        return set()
    if not predicate(grid[start[1]][start[0]]):
        return set()
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for n in neighbors4(x, y, width, height):
            if n not in seen and predicate(grid[n[1]][n[0]]):
                seen.add(n)
                stack.append(n)
    return seen

def connected_components(grid, predicate):
    height = len(grid)
    width = len(grid[0]) if height else 0
    remaining = {(x, y) for y in range(height) for x in range(width) if predicate(grid[y][x])}
    components = []
    while remaining:
        start = next(iter(remaining))
        comp = flood_fill(grid, start, predicate)
        components.append(comp)
        remaining -= comp
    return components

def dilate(mask, radius=1):
    height = len(mask)
    width = len(mask[0]) if height else 0
    out = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if mask[y][x]:
                for yy in range(max(0, y - radius), min(height, y + radius + 1)):
                    for xx in range(max(0, x - radius), min(width, x + radius + 1)):
                        out[yy][xx] = True
    return out

def erode(mask, radius=1):
    height = len(mask)
    width = len(mask[0]) if height else 0
    out = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            ok = True
            for yy in range(y - radius, y + radius + 1):
                for xx in range(x - radius, x + radius + 1):
                    if not (0 <= xx < width and 0 <= yy < height and mask[yy][xx]):
                        ok = False
            out[y][x] = ok
    return out

def occupancy_entropy(probabilities):
    total = 0.0
    for row in probabilities:
        for p in row:
            if 0 < p < 1:
                total -= p * math.log2(p) + (1 - p) * math.log2(1 - p)
    return total

def map_difference(a, b):
    if len(a) != len(b) or any((len(x) != len(y) for x, y in zip(a, b))):
        raise ValueError('shape')
    return [(x, y, a[y][x], b[y][x]) for y in range(len(a)) for x in range(len(a[y])) if a[y][x] != b[y][x]]

def downsample_grid(grid, factor):
    if factor <= 0:
        raise ValueError('factor')
    out = []
    for y in range(0, len(grid), factor):
        row = []
        for x in range(0, len(grid[y]), factor):
            cells = [grid[yy][xx] for yy in range(y, min(y + factor, len(grid))) for xx in range(x, min(x + factor, len(grid[yy])))]
            row.append(sum(cells) / len(cells))
        out.append(row)
    return out

def crop_grid(grid, x0, y0, x1, y1):
    return [row[x0:x1] for row in grid[y0:y1]]

def transpose_grid(grid):
    return [list(col) for col in zip(*grid)] if grid else []

def rotate_grid_right(grid):
    return [list(reversed(col)) for col in zip(*grid)] if grid else []

def histogram(grid):
    out = {}
    for row in grid:
        for value in row:
            out[value] = out.get(value, 0) + 1
    return out
