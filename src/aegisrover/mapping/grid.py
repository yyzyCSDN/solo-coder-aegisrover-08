from dataclasses import dataclass
from aegisrover.core.types import GridShape, Vec2

@dataclass
class OccupancyGrid:
    shape: GridShape
    cells: list[int]

    @classmethod
    def empty(cls, shape, fill=-1):
        shape.validate()
        return cls(shape, [fill] * (shape.width * shape.height))

    def index(self, x, y):
        if not (0 <= x < self.shape.width and 0 <= y < self.shape.height):
            raise IndexError((x, y))
        return y * self.shape.width + x

    def get(self, x, y):
        return self.cells[self.index(x, y)]

    def set(self, x, y, v):
        self.cells[self.index(x, y)] = int(v)

    def world_to_cell(self, p: Vec2):
        x = int((p.x - self.shape.origin.x) // self.shape.resolution)
        y = int((p.y - self.shape.origin.y) // self.shape.resolution)
        return (x, y)

    def cell_center(self, x, y):
        return Vec2(self.shape.origin.x + (x + 0.5) * self.shape.resolution, self.shape.origin.y + (y + 0.5) * self.shape.resolution)

    def neighbors4(self, x, y):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = (x + dx, y + dy)
            if 0 <= nx < self.shape.width and 0 <= ny < self.shape.height:
                yield (nx, ny)
