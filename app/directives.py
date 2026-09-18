"""Deterministic directive compilation from spec.md section 9."""

from dataclasses import dataclass
from math import inf

from app.schemas import DirectiveInterpretation, OptimizeRequest


@dataclass(frozen=True, slots=True)
class HourlyBounds:
    """All effective optimizer bounds for one hour."""

    hour: int
    effective_solar_kwh: float
    battery_lower_bound_kwh: float
    charge_upper_bound_kwh: float
    discharge_upper_bound_kwh: float
    grid_upper_bound_kwh: float


def compile_directives(
    request: OptimizeRequest,
    interpretations: list[DirectiveInterpretation],
) -> list[HourlyBounds]:
    """Compile validated directives into the most restrictive hourly bounds."""

    solar_factors: list[list[float]] = [[] for _ in range(24)]
    reserve_values: list[list[float]] = [[] for _ in range(24)]
    no_charge = [False] * 24
    no_discharge = [False] * 24
    grid_caps: list[list[float]] = [[] for _ in range(24)]

    for interpretation in interpretations:
        if not interpretation.applies:
            continue
        adjustment = interpretation.structured_adjustment
        if adjustment is None:
            continue
        hours = adjustment["hours"]
        directive_type = interpretation.directive_type

        for hour in hours:
            if directive_type == "solar_reduction":
                solar_factors[hour].append(float(adjustment["factor"]))
            elif directive_type == "minimum_battery_reserve":
                reserve_values[hour].append(
                    float(adjustment["minimum_energy_kwh"])
                )
            elif directive_type == "no_charge_window":
                no_charge[hour] = True
            elif directive_type == "no_discharge_window":
                no_discharge[hour] = True
            elif directive_type == "max_grid_window":
                grid_caps[hour].append(float(adjustment["max_grid_kwh"]))

    bounds: list[HourlyBounds] = []
    battery = request.battery
    for hour, entry in enumerate(request.hours):
        factor = min(solar_factors[hour], default=1.0)
        reserve = max([battery.minimum_energy_kwh, *reserve_values[hour]])
        bounds.append(
            HourlyBounds(
                hour=hour,
                effective_solar_kwh=entry.solar_kwh * factor,
                battery_lower_bound_kwh=reserve,
                charge_upper_bound_kwh=(
                    0.0
                    if no_charge[hour]
                    else battery.max_charge_kwh_per_hour
                ),
                discharge_upper_bound_kwh=(
                    0.0
                    if no_discharge[hour]
                    else battery.max_discharge_kwh_per_hour
                ),
                grid_upper_bound_kwh=min(grid_caps[hour], default=inf),
            )
        )
    return bounds
