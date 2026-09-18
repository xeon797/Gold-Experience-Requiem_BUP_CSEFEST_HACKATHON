"""Deterministic compiler/optimizer tests using organizer reference outputs."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.directives import compile_directives
from app.main import construct_response
from app.optimizer import solve_energy_plan
from app.replay import validate_replay
from app.schemas import DirectiveInterpretation, OptimizeRequest


SAMPLE_CASES_PATH = (
    Path(__file__).parents[1]
    / "reference"
    / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
)
SAMPLE_CASES = json.loads(SAMPLE_CASES_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", SAMPLE_CASES, ids=lambda case: case["id"])
def test_public_sample_optimizer_matches_reference_cost(case: dict) -> None:
    request = OptimizeRequest.model_validate(case["input"])
    interpretations = [
        DirectiveInterpretation.model_validate(item)
        for item in case["expected_output"]["directive_interpretation"]
    ]

    compiled = compile_directives(request, interpretations)
    solution = solve_energy_plan(request, compiled)
    response = construct_response(request, interpretations, solution)

    validate_replay(request, response)
    assert response.total_cost_bdt == pytest.approx(
        case["expected_output"]["total_cost_bdt"], abs=0.01
    )


def test_overlapping_directives_use_most_restrictive_bounds() -> None:
    case_input = deepcopy(SAMPLE_CASES[0]["input"])
    case_input["operator_notes"] = ["solar one", "solar two", "other limits"]
    request = OptimizeRequest.model_validate(case_input)
    interpretations = [
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12], "factor": 0.8},
            explanation="first cap",
        ),
        DirectiveInterpretation(
            note_index=1,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12], "factor": 0.5},
            explanation="second cap",
        ),
        DirectiveInterpretation(
            note_index=2,
            applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment={"hours": [12], "minimum_energy_kwh": 75},
            explanation="reserve",
        ),
    ]

    compiled = compile_directives(request, interpretations)
    hour_12 = compiled[12]

    assert hour_12.effective_solar_kwh == pytest.approx(
        request.hours[12].solar_kwh * 0.5
    )
    assert hour_12.battery_lower_bound_kwh == 75

