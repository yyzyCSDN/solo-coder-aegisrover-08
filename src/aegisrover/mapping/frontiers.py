def frontiers(grid):
    out = []
    for y in range(grid.shape.height):
        for x in range(grid.shape.width):
            if grid.get(x, y) == -1 and any((grid.get(nx, ny) >= 0 and grid.get(nx, ny) < 50 for nx, ny in grid.neighbors4(x, y))):
                out.append((x, y))
    return out
