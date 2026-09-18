"""Battery bookkeeping and thermal power limits.

Coulomb counting must be independent of the telemetry period: integrating 30 minutes
of current in one step has to move the state of charge exactly as much as 1800
one-second steps. Thermal derating must fall monotonically with temperature — a
curve that dips hardest just above the threshold and recovers near shutdown would
push full power into a hot pack.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

__all__ = ('BatteryPack', 'PowerBudget', 'thermal_factor', 'power_limit', 'DeratingCurve')


@dataclass
class BatteryPack:
    capacity_ah: float
    soc: float = 1.0
    charge_efficiency: float = 0.99
    discharge_efficiency: float = 0.99
    nominal_voltage: float = 48.0
    energy_used_wh: float = 0.0
    sampled_seconds: float = 0.0

    def __post_init__(self):
        if self.capacity_ah <= 0:
            raise ValueError('capacity must be positive')
        if not 0.0 <= self.soc <= 1.0:
            raise ValueError('soc must be within 0..1')
        if not 0.0 < self.charge_efficiency <= 1.0 or not 0.0 < self.discharge_efficiency <= 1.0:
            raise ValueError('efficiencies must be within (0, 1]')

    @property
    def remaining_ah(self) -> float:
        return self.soc * self.capacity_ah

    @property
    def remaining_wh(self) -> float:
        return self.remaining_ah * self.nominal_voltage

    def integrate(self, current_a: float, dt_seconds: float) -> float:
        """Positive current discharges the pack; the result is period independent."""
        if dt_seconds < 0:
            raise ValueError('dt must not be negative')
        hours = dt_seconds / 3600.0
        if current_a >= 0:
            used_ah = current_a * hours / self.discharge_efficiency
            self.soc -= used_ah / self.capacity_ah
            self.energy_used_wh += used_ah * self.nominal_voltage
        else:
            stored_ah = -current_a * hours * self.charge_efficiency
            self.soc += stored_ah / self.capacity_ah
        self.sampled_seconds += dt_seconds
        self.soc = min(1.0, max(0.0, self.soc))
        return self.soc

    def integrate_series(self, samples: Iterable[tuple[float, float]]) -> float:
        for current, dt in samples:
            self.integrate(current, dt)
        return self.soc

    def runtime_seconds(self, current_a: float, *, reserve: float = 0.1) -> float:
        if current_a <= 0:
            return math.inf
        usable = self.remaining_ah - reserve * self.capacity_ah
        if usable <= 0:
            return 0.0
        return usable / (current_a / self.discharge_efficiency) * 3600.0

    def distance_remaining(self, *, consumption_wh_per_m: float) -> float:
        if consumption_wh_per_m <= 0:
            raise ValueError('consumption must be positive')
        return self.remaining_wh / consumption_wh_per_m

    def to_dict(self) -> dict:
        return {'soc': round(self.soc, 9), 'remaining_ah': round(self.remaining_ah, 6),
                'remaining_wh': round(self.remaining_wh, 6),
                'energy_used_wh': round(self.energy_used_wh, 6),
                'sampled_seconds': round(self.sampled_seconds, 6)}


def thermal_factor(temp_c: float, start_c: float, shutdown_c: float) -> float:
    """1.0 below the threshold, 0.0 at shutdown, linear and monotone in between."""
    if shutdown_c <= start_c:
        raise ValueError('shutdown must be above the derating start')
    if temp_c <= start_c:
        return 1.0
    if temp_c >= shutdown_c:
        return 0.0
    return (shutdown_c - temp_c) / (shutdown_c - start_c)


def power_limit(nominal: float, temp_c: float, start_c: float, shutdown_c: float, *,
                caps: Iterable[float] = ()) -> float:
    limit = nominal * thermal_factor(temp_c, start_c, shutdown_c)
    for cap in caps:
        limit = min(limit, cap)
    return max(0.0, limit)


@dataclass
class DeratingCurve:
    start_c: float
    shutdown_c: float
    nominal: float
    extra_caps: tuple[tuple[float, float], ...] = field(default_factory=tuple)

    def factor(self, temp_c: float) -> float:
        return thermal_factor(temp_c, self.start_c, self.shutdown_c)

    def limit(self, temp_c: float) -> float:
        caps = [cap for threshold, cap in self.extra_caps if temp_c >= threshold]
        return power_limit(self.nominal, temp_c, self.start_c, self.shutdown_c, caps=caps)

    def is_monotone(self, *, low: float | None = None, high: float | None = None,
                    steps: int = 200) -> bool:
        low = self.start_c - 10.0 if low is None else low
        high = self.shutdown_c + 10.0 if high is None else high
        previous = math.inf
        for i in range(steps + 1):
            temp = low + (high - low) * i / steps
            value = self.limit(temp)
            if value > previous + 1e-9:
                return False
            previous = value
        return True

    def to_dict(self) -> dict:
        return {'start_c': self.start_c, 'shutdown_c': self.shutdown_c, 'nominal': self.nominal,
                'extra_caps': [list(item) for item in self.extra_caps]}


@dataclass(frozen=True)
class PowerBudget:
    available_w: float
    thermal_factor: float
    binding_constraint: str

    def to_dict(self) -> dict:
        return {'available_w': round(self.available_w, 6),
                'thermal_factor': round(self.thermal_factor, 6),
                'binding_constraint': self.binding_constraint}


def budget(nominal: float, temp_c: float, curve: DeratingCurve) -> PowerBudget:
    limit = curve.limit(temp_c)
    if limit >= nominal - 1e-9:
        constraint = 'none'
    elif curve.factor(temp_c) * nominal <= limit + 1e-9:
        constraint = 'thermal'
    else:
        constraint = 'cap'
    return PowerBudget(limit, curve.factor(temp_c), constraint)
