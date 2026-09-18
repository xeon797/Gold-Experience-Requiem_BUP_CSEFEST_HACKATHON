"""End-to-end API contract tests for the optimized endpoint."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app, get_interpreter
from app.replay import ReplayValidationError, validate_replay
from app.schemas import DirectiveInterpretation, OptimizeRequest, OptimizeResponse


SAMPLE_CASES_PATH = (
    Path(__file__).parents[1]
    / "reference"
    / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
)


@pytest.fixture
def sample_input() -> dict:
    document = json.loads(SAMPLE_CASES_PATH.read_text(encoding="utf-8"))
    return deepcopy(document["cases"][0]["input"])


class FakeInterpreter:
    async def interpret(
        self, operator_notes: list[str], battery_capacity_kwh: float
    ) -> list[DirectiveInterpretation]:
        del battery_capacity_kwh
        return [
            DirectiveInterpretation(
                note_index=index,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation="test stub",
            )
            for index, _note in enumerate(operator_notes)
        ]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    get_settings.cache_clear()
    app.dependency_overrides[get_interpreter] = lambda: FakeInterpreter()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_optimize_energy_returns_exact_schema(
    client: TestClient, sample_input: dict
) -> None:
    response = client.post("/optimize-energy", json=sample_input)

    assert response.status_code == 200
    body = response.json()
    validated = OptimizeResponse.model_validate(body)
    assert set(body) == {
        "scenario_id",
        "directive_interpretation",
        "hourly_plan",
        "total_grid_kwh",
        "total_cost_bdt",
        "peak_grid_kwh",
        "plan_summary",
    }
    assert [entry.hour for entry in validated.hourly_plan] == list(range(24))
    assert len(validated.directive_interpretation) == len(
        sample_input["operator_notes"]
    )

    request_model = OptimizeRequest.model_validate(sample_input)
    validate_replay(request_model, validated)

    grid_only_cost = sum(
        entry["demand_kwh"] * entry["tariff_bdt_per_kwh"]
        for entry in sample_input["hours"]
    )
    assert validated.total_cost_bdt <= grid_only_cost
    assert "optimization not yet implemented" not in validated.plan_summary


def test_structurally_invalid_request_returns_sanitized_400(
    client: TestClient, sample_input: dict
) -> None:
    sample_input["hours"].pop()

    response = client.post("/optimize-energy", json=sample_input)

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error", "message", "details"}
    assert body["error"] == "invalid_request"
    serialized_body = response.text.lower()
    assert "traceback" not in serialized_body
    assert "pydantic" not in serialized_body
    assert "exception" not in serialized_body


def test_replay_failure_returns_sanitized_500(
    client: TestClient,
    sample_input: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_replay(*_args: object) -> None:
        raise ReplayValidationError("internal replay detail must remain private")

    monkeypatch.setattr("app.main.validate_replay", fail_replay)
    response = client.post("/optimize-energy", json=sample_input)

    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_error",
        "message": "Internal processing failed.",
    }
    assert "internal replay detail" not in response.text
