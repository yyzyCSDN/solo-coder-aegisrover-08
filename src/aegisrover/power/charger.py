def charge_time(capacity_ah, soc, target, current_a, efficiency=0.9):
    if not 0 <= soc <= target <= 1:
        raise ValueError('soc')
    return capacity_ah * (target - soc) / (current_a * efficiency) * 3600

def can_start(soc, reserve, required):
    return soc - reserve >= required
