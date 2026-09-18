"""Unit tests for the request schemas defined by the organizer contract."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import OptimizeRequest


SAMPLE_CASES_PATH = (
    Path(__file__).parents[1]
    / "reference"
    / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
)


@pytest.fixture
def valid_request_data() -> dict:
    document = json.loads(SAMPLE_CASES_PATH.read_text(encoding="utf-8"))
    return deepcopy(document["cases"][0]["input"])


def test_valid_request_passes_and_normalizes_hours(valid_request_data: dict) -> None:
    valid_request_data["hours"].reverse()

    request = OptimizeRequest.model_validate(valid_request_data)

    assert [entry.hour for entry in request.hours] == list(range(24))


def test_missing_hour_is_rejected(valid_request_data: dict) -> None:
    valid_request_data["hours"][-1]["hour"] = 24

    with pytest.raises(ValidationError):
        OptimizeRequest.model_validate(valid_request_data)


def test_duplicate_hour_is_rejected(valid_request_data: dict) -> None:
    valid_request_data["hours"][-1]["hour"] = 22

    with pytest.raises(ValidationError):
        OptimizeRequest.model_validate(valid_request_data)


def test_23_hours_are_rejected(valid_request_data: dict) -> None:
    valid_request_data["hours"].pop()

    with pytest.raises(ValidationError):
        OptimizeRequest.model_validate(valid_request_data)


@pytest.mark.parametrize("note_count", [0, 4])
def test_operator_note_count_out_of_range_is_rejected(
    valid_request_data: dict, note_count: int
) -> None:
    valid_request_data["operator_notes"] = ["note"] * note_count

    with pytest.raises(ValidationError):
        OptimizeRequest.model_validate(valid_request_data)


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numeric_value_is_rejected(
    valid_request_data: dict, invalid_value: float
) -> None:
    valid_request_data["hours"][0]["demand_kwh"] = invalid_value

    with pytest.raises(ValidationError):
        OptimizeRequest.model_validate(valid_request_data)


def test_minimum_energy_above_capacity_is_rejected(valid_request_data: dict) -> None:
    valid_request_data["battery"]["minimum_energy_kwh"] = 221
    valid_request_data["battery"]["initial_energy_kwh"] = 221

    with pytest.raises(ValidationError):
        OptimizeRequest.model_validate(valid_request_data)


def test_unknown_top_level_field_is_rejected(valid_request_data: dict) -> None:
    valid_request_data["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        OptimizeRequest.model_validate(valid_request_data)
