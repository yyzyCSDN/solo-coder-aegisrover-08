import math

def charging_efficiency(input_wh, stored_wh):
    return 0.0 if input_wh <= 0 else max(0.0, min(1.0, stored_wh / input_wh))

def reserve_margin(soc, reserve):
    return soc - reserve
