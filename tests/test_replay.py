"""Independent replay validation tests for valid and corrupted plans."""

from copy import deepcopy

import pytest

from app.replay import ReplayValidationError, validate_replay
from app.schemas import (
    DirectiveInterpretation,
    OptimizeRequest,
    OptimizeResponse,
)


def _request(note: str = "Nothing relevant") -> OptimizeRequest:
    return OptimizeRequest.model_validate(
        {
            "scenario_id": "REPLAY-TEST",
            "operator_notes": [note],
            "hours": [
                {
                    "hour": hour,
                    "demand_kwh": 10,
                    "solar_kwh": 0,
                    "tariff_bdt_per_kwh": 1,
                }
                for hour in range(24)
            ],
            "battery": {
                "capacity_kwh": 10,
                "initial_energy_kwh": 5,
                "minimum_energy_kwh": 0,
                "max_charge_kwh_per_hour": 5,
                "max_discharge_kwh_per_hour": 5,
            },
        }
    )


def _interpretation(
    directive_type: str = "no_op",
    adjustment: dict | None = None,
) -> DirectiveInterpretation:
    return DirectiveInterpretation(
        note_index=0,
        applies=directive_type != "no_op",
        directive_type=directive_type,
        structured_adjustment=adjustment,
        explanation="test interpretation",
    )


def _valid_response(
    interpretation: DirectiveInterpretation | None = None,
) -> OptimizeResponse:
    return OptimizeResponse.model_validate(
        {
            "scenario_id": "REPLAY-TEST",
            "directive_interpretation": [interpretation or _interpretation()],
            "hourly_plan": [
                {
                    "hour": hour,
                    "grid_kwh": 10,
                    "solar_used_kwh": 0,
                    "battery_action": "idle",
                    "battery_kwh": 0,
                    "battery_energy_after_kwh": 5,
                }
                for hour in range(24)
            ],
            "total_grid_kwh": 240,
            "total_cost_bdt": 240,
            "peak_grid_kwh": 10,
            "plan_summary": "Valid hand-built replay fixture.",
        }
    )


def test_valid_hand_built_plan_passes_replay() -> None:
    validate_replay(_request(), _valid_response())


def test_replay_catches_energy_balance_violation() -> None:
    response = deepcopy(_valid_response())
    response.hourly_plan[0].grid_kwh = 9

    with pytest.raises(ReplayValidationError, match="energy balance"):
        validate_replay(_request(), response)


def test_replay_catches_directive_reserve_violation() -> None:
    interpretation = _interpretation(
        "minimum_battery_reserve",
        {"hours": [0], "minimum_energy_kwh": 6},
    )

    with pytest.raises(ReplayValidationError, match="directive reserve"):
        validate_replay(
            _request("Maintain an emergency reserve."),
            _valid_response(interpretation),
        )


def test_replay_catches_no_charge_violation() -> None:
    request = _request("Do not charge in hour zero.")
    interpretation = _interpretation("no_charge_window", {"hours": [0]})
    response = deepcopy(_valid_response(interpretation))
    response.hourly_plan[0].grid_kwh = 11
    response.hourly_plan[0].battery_action = "charge"
    response.hourly_plan[0].battery_kwh = 1
    response.hourly_plan[0].battery_energy_after_kwh = 6
    response.hourly_plan[1].grid_kwh = 9
    response.hourly_plan[1].battery_action = "discharge"
    response.hourly_plan[1].battery_kwh = 1
    response.hourly_plan[1].battery_energy_after_kwh = 5

    with pytest.raises(ReplayValidationError, match="no-charge directive"):
        validate_replay(request, response)


def test_replay_catches_mismatched_totals() -> None:
    response = deepcopy(_valid_response())
    response.total_cost_bdt = 239

    with pytest.raises(ReplayValidationError, match="total_cost_bdt"):
        validate_replay(_request(), response)


def test_replay_catches_non_neutral_end_of_day_energy() -> None:
    response = deepcopy(_valid_response())
    final = response.hourly_plan[23]
    final.grid_kwh = 11
    final.battery_action = "charge"
    final.battery_kwh = 1
    final.battery_energy_after_kwh = 6
    response.total_grid_kwh = 241
    response.total_cost_bdt = 241
    response.peak_grid_kwh = 11

    with pytest.raises(ReplayValidationError, match="end-of-day neutrality"):
        validate_replay(_request(), response)

