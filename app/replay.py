"""Independent serialized-plan replay validator from spec.md section 12."""

from dataclasses import dataclass
from math import fsum, inf, isfinite

from app.schemas import OptimizeRequest, OptimizeResponse


REPLAY_TOLERANCE = 0.001


class ReplayValidationError(Exception):
    """Raised internally when a serialized response fails independent replay."""


@dataclass(slots=True)
class _ReplayLimits:
    effective_solar: list[float]
    directive_reserve: list[float]
    no_charge: list[bool]
    no_discharge: list[bool]
    grid_cap: list[float]


def _derive_limits(response: OptimizeResponse, request: OptimizeRequest) -> _ReplayLimits:
    effective_solar = [entry.solar_kwh for entry in request.hours]
    solar_factors: list[list[float]] = [[] for _ in range(24)]
    directive_reserve = [request.battery.minimum_energy_kwh] * 24
    no_charge = [False] * 24
    no_discharge = [False] * 24
    grid_cap = [inf] * 24

    try:
        for interpretation in response.directive_interpretation:
            if not interpretation.applies:
                continue
            adjustment = interpretation.structured_adjustment
            if adjustment is None:
                raise ReplayValidationError(
                    "active directive has no structured adjustment"
                )
            directive_type = interpretation.directive_type
            for hour in adjustment["hours"]:
                if directive_type == "solar_reduction":
                    solar_factors[hour].append(float(adjustment["factor"]))
                elif directive_type == "minimum_battery_reserve":
                    directive_reserve[hour] = max(
                        directive_reserve[hour],
                        float(adjustment["minimum_energy_kwh"]),
                    )
                elif directive_type == "no_charge_window":
                    no_charge[hour] = True
                elif directive_type == "no_discharge_window":
                    no_discharge[hour] = True
                elif directive_type == "max_grid_window":
                    grid_cap[hour] = min(
                        grid_cap[hour], float(adjustment["max_grid_kwh"])
                    )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ReplayValidationError(
            "directive interpretation could not be independently replayed"
        ) from exc

    for hour in range(24):
        effective_solar[hour] *= min(solar_factors[hour], default=1.0)
    return _ReplayLimits(
        effective_solar=effective_solar,
        directive_reserve=directive_reserve,
        no_charge=no_charge,
        no_discharge=no_discharge,
        grid_cap=grid_cap,
    )


def _finite_nonnegative(value: float, field: str, hour: int | None = None) -> None:
    location = f" at hour {hour}" if hour is not None else ""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayValidationError(f"{field}{location} must be numeric")
    if not isfinite(value) or value < 0:
        raise ReplayValidationError(
            f"{field}{location} must be finite and non-negative"
        )


def _close(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= REPLAY_TOLERANCE


def validate_replay(request: OptimizeRequest, response: OptimizeResponse) -> None:
    """Replay the emitted response without trusting compiler or solver state."""

    if response.scenario_id != request.scenario_id:
        raise ReplayValidationError("scenario_id does not match the request")
    if len(response.hourly_plan) != 24:
        raise ReplayValidationError("hourly plan must contain exactly 24 entries")
    plan_hours = [entry.hour for entry in response.hourly_plan]
    if len(set(plan_hours)) != 24 or set(plan_hours) != set(range(24)):
        raise ReplayValidationError("hourly plan hours must be unique 0 through 23")

    plan = sorted(response.hourly_plan, key=lambda entry: entry.hour)
    request_hours = {entry.hour: entry for entry in request.hours}
    limits = _derive_limits(response, request)
    previous_energy = request.battery.initial_energy_kwh

    for entry in plan:
        hour = entry.hour
        source = request_hours[hour]
        _finite_nonnegative(entry.grid_kwh, "grid_kwh", hour)
        _finite_nonnegative(entry.solar_used_kwh, "solar_used_kwh", hour)
        _finite_nonnegative(entry.battery_kwh, "battery_kwh", hour)
        _finite_nonnegative(
            entry.battery_energy_after_kwh,
            "battery_energy_after_kwh",
            hour,
        )

        if entry.battery_action == "idle":
            if entry.battery_kwh != 0:
                raise ReplayValidationError(
                    f"idle battery action must have zero battery_kwh at hour {hour}"
                )
            signed_change = 0.0
        elif entry.battery_action == "charge":
            if entry.battery_kwh <= 0:
                raise ReplayValidationError(
                    f"charge action must have positive battery_kwh at hour {hour}"
                )
            signed_change = entry.battery_kwh
        elif entry.battery_action == "discharge":
            if entry.battery_kwh <= 0:
                raise ReplayValidationError(
                    f"discharge action must have positive battery_kwh at hour {hour}"
                )
            signed_change = -entry.battery_kwh
        else:
            raise ReplayValidationError(f"invalid battery action at hour {hour}")

        expected_energy = previous_energy + signed_change
        if not _close(entry.battery_energy_after_kwh, expected_energy):
            raise ReplayValidationError(
                f"battery transition mismatch at hour {hour}"
            )
        if (
            entry.battery_energy_after_kwh
            > request.battery.capacity_kwh + REPLAY_TOLERANCE
        ):
            raise ReplayValidationError(f"battery capacity exceeded at hour {hour}")
        if (
            entry.battery_energy_after_kwh
            < request.battery.minimum_energy_kwh - REPLAY_TOLERANCE
        ):
            raise ReplayValidationError(f"base battery reserve violated at hour {hour}")
        if (
            entry.battery_energy_after_kwh
            < limits.directive_reserve[hour] - REPLAY_TOLERANCE
        ):
            raise ReplayValidationError(f"directive reserve violated at hour {hour}")

        if (
            entry.battery_action == "charge"
            and entry.battery_kwh
            > request.battery.max_charge_kwh_per_hour + REPLAY_TOLERANCE
        ):
            raise ReplayValidationError(f"charge rate limit violated at hour {hour}")
        if (
            entry.battery_action == "discharge"
            and entry.battery_kwh
            > request.battery.max_discharge_kwh_per_hour + REPLAY_TOLERANCE
        ):
            raise ReplayValidationError(
                f"discharge rate limit violated at hour {hour}"
            )
        if limits.no_charge[hour] and entry.battery_action == "charge":
            raise ReplayValidationError(f"no-charge directive violated at hour {hour}")
        if limits.no_discharge[hour] and entry.battery_action == "discharge":
            raise ReplayValidationError(
                f"no-discharge directive violated at hour {hour}"
            )
        if entry.grid_kwh > limits.grid_cap[hour] + REPLAY_TOLERANCE:
            raise ReplayValidationError(f"grid-cap directive violated at hour {hour}")
        if (
            entry.solar_used_kwh
            > limits.effective_solar[hour] + REPLAY_TOLERANCE
        ):
            raise ReplayValidationError(
                f"solar-reduction availability violated at hour {hour}"
            )

        balance_left = entry.grid_kwh + entry.solar_used_kwh
        balance_right = source.demand_kwh + signed_change
        if not _close(balance_left, balance_right):
            raise ReplayValidationError(f"energy balance violated at hour {hour}")
        previous_energy = entry.battery_energy_after_kwh

    if not _close(previous_energy, request.battery.initial_energy_kwh):
        raise ReplayValidationError("end-of-day neutrality violated")

    recalculated_grid = fsum(entry.grid_kwh for entry in plan)
    recalculated_cost = fsum(
        entry.grid_kwh * request_hours[entry.hour].tariff_bdt_per_kwh
        for entry in plan
    )
    recalculated_peak = max(entry.grid_kwh for entry in plan)
    for value, field in (
        (response.total_grid_kwh, "total_grid_kwh"),
        (response.total_cost_bdt, "total_cost_bdt"),
        (response.peak_grid_kwh, "peak_grid_kwh"),
    ):
        _finite_nonnegative(value, field)
    if not _close(response.total_grid_kwh, recalculated_grid):
        raise ReplayValidationError("total_grid_kwh does not match hourly plan")
    if not _close(response.total_cost_bdt, recalculated_cost):
        raise ReplayValidationError("total_cost_bdt does not match hourly plan")
    if not _close(response.peak_grid_kwh, recalculated_peak):
        raise ReplayValidationError("peak_grid_kwh does not match hourly plan")
