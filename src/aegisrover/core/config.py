from aegisrover.core.units import convert
SCHEMA = {'max_speed': ('m/s', 0.0, 5.0), 'wheel_base': ('m', 0.05, 3.0), 'max_yaw_rate': ('rad', 0.0, 6.3), 'battery_reserve': ('ratio', 0.0, 1.0)}

def normalize(config):
    out = {}
    for key, (unit, lo, hi) in SCHEMA.items():
        raw = config[key]
        if isinstance(raw, dict):
            value = convert(float(raw['value']), raw['unit'], unit)
        else:
            value = float(raw)
        if not lo <= value <= hi:
            raise ValueError(key)
        out[key] = value
    return out
