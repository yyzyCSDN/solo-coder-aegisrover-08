from dataclasses import dataclass
import math
_FACTORS = {('m', 'm'): 1.0, ('cm', 'm'): 0.01, ('mm', 'm'): 0.001, ('km', 'm'): 1000.0, ('s', 's'): 1.0, ('ms', 's'): 0.001, ('min', 's'): 60.0, ('deg', 'rad'): math.pi / 180.0, ('rad', 'rad'): 1.0, ('km/h', 'm/s'): 1000.0 / 3600.0, ('m/s', 'm/s'): 1.0, ('percent', 'ratio'): 0.01, ('ratio', 'ratio'): 1.0}

def convert(value: float, src: str, dst: str) -> float:
    if src == dst:
        return float(value)
    if (src, dst) in _FACTORS:
        return float(value) * _FACTORS[src, dst]
    inv = (dst, src)
    if inv in _FACTORS:
        return float(value) / _FACTORS[inv]
    raise ValueError(f'incompatible units: {src}->{dst}')

@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str

    def to(self, unit: str) -> 'Quantity':
        return Quantity(convert(self.value, self.unit, unit), unit)
