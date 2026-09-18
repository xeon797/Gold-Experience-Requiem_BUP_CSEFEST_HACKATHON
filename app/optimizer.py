"""Lossless 24-hour linear energy optimizer from spec.md section 10."""

from dataclasses import dataclass
import logging
from math import isfinite

import numpy as np
from scipy.optimize import linprog

from app.directives import HourlyBounds
from app.errors import InternalProcessingError
from app.schemas import OptimizeRequest


logger = logging.getLogger(__name__)
HOURS = 24


@dataclass(frozen=True, slots=True)
class SolverHour:
    """Canonical raw solver values for one hour."""

    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_change_kwh: float
    battery_energy_after_kwh: float


def solve_energy_plan(
    request: OptimizeRequest,
    hourly_bounds: list[HourlyBounds],
) -> list[SolverHour]:
    """Minimize grid cost without relaxing any compiled hard constraint."""

    if len(hourly_bounds) != HOURS:
        raise InternalProcessingError("Energy optimization failed.")

    grid_offset = 0
    solar_offset = HOURS
    change_offset = 2 * HOURS
    energy_offset = 3 * HOURS
    variable_count = 4 * HOURS

    objective = np.zeros(variable_count)
    for hour, entry in enumerate(request.hours):
        objective[grid_offset + hour] = entry.tariff_bdt_per_kwh

    equality_rows: list[np.ndarray] = []
    equality_values: list[float] = []

    for hour, entry in enumerate(request.hours):
        balance = np.zeros(variable_count)
        balance[grid_offset + hour] = 1.0
        balance[solar_offset + hour] = 1.0
        balance[change_offset + hour] = -1.0
        equality_rows.append(balance)
        equality_values.append(entry.demand_kwh)

        state = np.zeros(variable_count)
        state[energy_offset + hour] = 1.0
        state[change_offset + hour] = -1.0
        if hour == 0:
            equality_values.append(request.battery.initial_energy_kwh)
        else:
            state[energy_offset + hour - 1] = -1.0
            equality_values.append(0.0)
        equality_rows.append(state)

    neutrality = np.zeros(variable_count)
    neutrality[energy_offset + 23] = 1.0
    equality_rows.append(neutrality)
    equality_values.append(request.battery.initial_energy_kwh)

    variable_bounds: list[tuple[float | None, float | None]] = []
    variable_bounds.extend(
        (
            0.0,
            None
            if not isfinite(bound.grid_upper_bound_kwh)
            else bound.grid_upper_bound_kwh,
        )
        for bound in hourly_bounds
    )
    variable_bounds.extend(
        (0.0, bound.effective_solar_kwh) for bound in hourly_bounds
    )
    variable_bounds.extend(
        (-bound.discharge_upper_bound_kwh, bound.charge_upper_bound_kwh)
        for bound in hourly_bounds
    )
    variable_bounds.extend(
        (bound.battery_lower_bound_kwh, request.battery.capacity_kwh)
        for bound in hourly_bounds
    )

    result = linprog(
        objective,
        A_eq=np.vstack(equality_rows),
        b_eq=np.asarray(equality_values),
        bounds=variable_bounds,
        method="highs",
    )
    if not result.success or result.status != 0 or result.x is None:
        logger.error(
            "Energy optimizer failed with status=%s message=%s",
            result.status,
            result.message,
        )
        raise InternalProcessingError("Energy optimization failed.")
    if not np.all(np.isfinite(result.x)):
        logger.error("Energy optimizer returned non-finite decision variables.")
        raise InternalProcessingError("Energy optimization failed.")

    return [
        SolverHour(
            hour=hour,
            grid_kwh=float(result.x[grid_offset + hour]),
            solar_used_kwh=float(result.x[solar_offset + hour]),
            battery_change_kwh=float(result.x[change_offset + hour]),
            battery_energy_after_kwh=float(result.x[energy_offset + hour]),
        )
        for hour in range(HOURS)
    ]
