"""Pure deterministic tests for untrusted LLM interpretation output."""

from copy import deepcopy

import pytest

from app.guardrails import GuardrailValidationError, validate_interpretations


@pytest.fixture
def valid_output() -> list[dict]:
    return [
        {
            "note_index": 1,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "The note is unrelated to this energy schedule.",
        },
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
            "explanation": "Solar availability is reduced for two hours.",
        },
    ]


def test_valid_output_is_sorted_by_note_index(valid_output: list[dict]) -> None:
    result = validate_interpretations(
        valid_output, expected_count=2, battery_capacity_kwh=500
    )

    assert [entry.note_index for entry in result] == [0, 1]


def test_missing_note_index_is_rejected(valid_output: list[dict]) -> None:
    del valid_output[0]["note_index"]

    with pytest.raises(GuardrailValidationError, match="exact fields"):
        validate_interpretations(valid_output, 2, 500)


def test_duplicate_note_index_is_rejected(valid_output: list[dict]) -> None:
    valid_output[0]["note_index"] = 0

    with pytest.raises(GuardrailValidationError, match="bijection"):
        validate_interpretations(valid_output, 2, 500)


@pytest.mark.parametrize(
    "adjustment",
    [
        {"hours": [13, 14]},
        {"hours": [13, 14], "factor": 0.2, "unexpected": True},
        {"hours": [13, 14], "minimum_energy_kwh": 20},
    ],
)
def test_wrong_structured_adjustment_shape_is_rejected(
    valid_output: list[dict], adjustment: dict
) -> None:
    valid_output[1]["structured_adjustment"] = adjustment

    with pytest.raises(GuardrailValidationError, match="exact keys"):
        validate_interpretations(valid_output, 2, 500)


@pytest.mark.parametrize("hours", [[13, 24], [14, 13], [13, 13]])
def test_invalid_hours_are_rejected(valid_output: list[dict], hours: list[int]) -> None:
    valid_output[1]["structured_adjustment"]["hours"] = hours

    with pytest.raises(GuardrailValidationError, match="hours"):
        validate_interpretations(valid_output, 2, 500)


def test_factor_above_one_is_rejected(valid_output: list[dict]) -> None:
    valid_output[1]["structured_adjustment"]["factor"] = 1.01

    with pytest.raises(GuardrailValidationError, match="factor"):
        validate_interpretations(valid_output, 2, 500)


def test_no_op_with_applies_true_is_rejected(valid_output: list[dict]) -> None:
    valid_output[0]["applies"] = True

    with pytest.raises(GuardrailValidationError, match="no_op"):
        validate_interpretations(valid_output, 2, 500)


def test_non_no_op_with_applies_false_is_rejected(valid_output: list[dict]) -> None:
    valid_output[1]["applies"] = False

    with pytest.raises(GuardrailValidationError, match="applies=true"):
        validate_interpretations(valid_output, 2, 500)


def test_reserve_above_battery_capacity_is_rejected(valid_output: list[dict]) -> None:
    reserve = deepcopy(valid_output[1])
    reserve["directive_type"] = "minimum_battery_reserve"
    reserve["structured_adjustment"] = {
        "hours": [18, 19, 20],
        "minimum_energy_kwh": 501,
    }
    valid_output[1] = reserve

    with pytest.raises(GuardrailValidationError, match="capacity"):
        validate_interpretations(valid_output, 2, 500)


def test_negative_grid_cap_is_rejected(valid_output: list[dict]) -> None:
    grid_cap = deepcopy(valid_output[1])
    grid_cap["directive_type"] = "max_grid_window"
    grid_cap["structured_adjustment"] = {
        "hours": [18],
        "max_grid_kwh": -1,
    }
    valid_output[1] = grid_cap

    with pytest.raises(GuardrailValidationError, match="max_grid_kwh"):
        validate_interpretations(valid_output, 2, 500)


def test_empty_explanation_is_rejected(valid_output: list[dict]) -> None:
    valid_output[0]["explanation"] = "   "

    with pytest.raises(GuardrailValidationError, match="explanation"):
        validate_interpretations(valid_output, 2, 500)


def test_non_list_output_is_rejected() -> None:
    with pytest.raises(GuardrailValidationError, match="JSON array"):
        validate_interpretations({"items": []}, 0, 500)
