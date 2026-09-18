"""Pydantic v2 request and response contracts from spec.md sections 5 and 6."""

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


def _require_json_number(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a JSON number")
    return value


NonNegativeFiniteNumber = Annotated[
    float,
    BeforeValidator(_require_json_number),
    Field(ge=0, allow_inf_nan=False),
]
HourNumber = Annotated[int, Field(ge=0, le=23, strict=True)]
NonEmptyIdentifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
NonEmptyNote = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]
BatteryAction = Literal["charge", "discharge", "idle"]


class ContractModel(BaseModel):
    """Base model that rejects fields outside the organizer contract."""

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(BaseModel):
    """Controlled error response payload for 400 and 500 status codes."""

    error: str = Field(description="Machine-readable error code")
    message: str | None = Field(default=None, description="Human-readable error explanation")
    details: list[dict[str, str]] | None = Field(
        default=None, description="Field-level validation error details"
    )


class HourEntry(ContractModel):
    """Demand, solar availability, and tariff for one input hour."""

    hour: HourNumber
    demand_kwh: NonNegativeFiniteNumber
    solar_kwh: NonNegativeFiniteNumber
    tariff_bdt_per_kwh: NonNegativeFiniteNumber


class Battery(ContractModel):
    """Battery capacity, initial state, reserve, and hourly rate limits."""

    capacity_kwh: NonNegativeFiniteNumber
    initial_energy_kwh: NonNegativeFiniteNumber
    minimum_energy_kwh: NonNegativeFiniteNumber
    max_charge_kwh_per_hour: NonNegativeFiniteNumber
    max_discharge_kwh_per_hour: NonNegativeFiniteNumber

    @model_validator(mode="after")
    def validate_energy_bounds(self) -> "Battery":
        if not (
            self.minimum_energy_kwh
            <= self.initial_energy_kwh
            <= self.capacity_kwh
        ):
            raise ValueError(
                "battery energy must satisfy minimum_energy_kwh <= "
                "initial_energy_kwh <= capacity_kwh"
            )
        return self


class OptimizeRequest(ContractModel):
    """Exact request body accepted by POST /optimize-energy."""

    scenario_id: NonEmptyIdentifier
    operator_notes: list[NonEmptyNote] = Field(min_length=1, max_length=3)
    hours: list[HourEntry] = Field(min_length=24, max_length=24)
    battery: Battery

    @model_validator(mode="after")
    def validate_and_sort_hours(self) -> "OptimizeRequest":
        hour_values = [entry.hour for entry in self.hours]
        if len(set(hour_values)) != 24 or set(hour_values) != set(range(24)):
            raise ValueError("hours must contain each integer from 0 through 23 once")
        self.hours = sorted(self.hours, key=lambda entry: entry.hour)
        return self


class DirectiveInterpretation(ContractModel):
    """One structured interpretation corresponding to one operator note."""

    note_index: Annotated[int, Field(ge=0, strict=True)]
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: dict[str, Any] | None
    explanation: NonEmptyText


class HourlyPlanEntry(ContractModel):
    """One serialized hourly action in an optimization response."""

    hour: HourNumber
    grid_kwh: NonNegativeFiniteNumber
    solar_used_kwh: NonNegativeFiniteNumber
    battery_action: BatteryAction
    battery_kwh: NonNegativeFiniteNumber
    battery_energy_after_kwh: NonNegativeFiniteNumber


class OptimizeResponse(ContractModel):
    """Exact successful response body returned by POST /optimize-energy."""

    scenario_id: NonEmptyIdentifier
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry] = Field(min_length=24, max_length=24)
    total_grid_kwh: NonNegativeFiniteNumber
    total_cost_bdt: NonNegativeFiniteNumber
    peak_grid_kwh: NonNegativeFiniteNumber
    plan_summary: NonEmptyText

    @model_validator(mode="after")
    def validate_and_sort_plan_hours(self) -> "OptimizeResponse":
        hour_values = [entry.hour for entry in self.hourly_plan]
        if len(set(hour_values)) != 24 or set(hour_values) != set(range(24)):
            raise ValueError(
                "hourly_plan must contain each integer from 0 through 23 once"
            )
        self.hourly_plan = sorted(self.hourly_plan, key=lambda entry: entry.hour)
        return self
