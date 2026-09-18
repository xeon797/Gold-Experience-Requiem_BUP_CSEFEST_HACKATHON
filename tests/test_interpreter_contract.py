"""Contract tests for the batched Gemini interpreter client."""

import asyncio
import json
import os

from dotenv import load_dotenv
import httpx
import pytest

from app.config import Settings, get_settings
from app.errors import InternalProcessingError
from app.interpreter import GeminiInterpreter, SYSTEM_PROMPT


def _settings() -> Settings:
    return Settings(
        gemini_api_key="test-only-key",
        gemini_model="gemini-3.1-flash-lite",
        gemini_base_url="https://generativelanguage.test/v1beta",
        llm_timeout_seconds=5,
        port=8000,
        log_level="INFO",
    )


def _api_response(content: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "role": "model",
                        "parts": [{"text": json.dumps(content)}],
                    },
                }
            ]
        },
    )


def test_system_prompt_contains_required_semantics() -> None:
    required_fragments = [
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
        "no_op",
        "start-inclusive and end-exclusive",
        "80% reduction",
        "reduced to 80%",
        "one-fifth remains",
        "untrusted input data",
        "battery capacity",
    ]

    for fragment in required_fragments:
        assert fragment in SYSTEM_PROMPT


def test_interpreter_batches_all_notes_in_one_json_mode_call() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return _api_response(
            [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "solar_reduction",
                    "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
                    "explanation": "Solar is reduced in the stated window.",
                },
                {
                    "note_index": 1,
                    "applies": False,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "The note is unrelated.",
                },
            ]
        )

    async def run() -> list:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            interpreter = GeminiInterpreter(_settings(), client=client)
            return await interpreter.interpret(
                ["Solar drops to 20% from 1 PM to 3 PM.", "Cafeteria update."],
                battery_capacity_kwh=500,
            )

    result = asyncio.run(run())

    assert len(requests) == 1
    generation_config = requests[0]["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseSchema"]["type"] == "ARRAY"
    variants = generation_config["responseSchema"]["items"]["anyOf"]
    assert len(variants) == 6
    solar_variant = next(
        variant
        for variant in variants
        if variant["properties"]["directive_type"]["enum"]
        == ["solar_reduction"]
    )
    solar_adjustment = solar_variant["properties"]["structured_adjustment"]
    assert set(solar_adjustment["properties"]) == {"hours", "factor"}
    assert generation_config["temperature"] == 0.1
    assert generation_config["maxOutputTokens"] == 1_200
    assert generation_config["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert "Solar drops to 20%" in requests[0]["contents"][0]["parts"][0]["text"]
    assert "Cafeteria update" in requests[0]["contents"][0]["parts"][0]["text"]
    assert SYSTEM_PROMPT == requests[0]["systemInstruction"]["parts"][0]["text"]
    assert [entry.note_index for entry in result] == [0, 1]


def test_interpreter_makes_exactly_one_repair_call() -> None:
    call_payloads: list[dict] = []
    responses = [
        [
            {
                "note_index": 0,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "Wrongly missing the second note.",
            }
        ],
        [
            {
                "note_index": 0,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "The first note is unrelated.",
            },
            {
                "note_index": 1,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "The second note is unrelated.",
            },
        ],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        call_payloads.append(json.loads(request.content))
        return _api_response(responses.pop(0))

    async def run() -> list:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            interpreter = GeminiInterpreter(_settings(), client=client)
            return await interpreter.interpret(["Note A", "Note B"], 500)

    result = asyncio.run(run())

    assert len(call_payloads) == 2
    assert len(call_payloads[1]["contents"]) == 3
    assert "failed deterministic validation" in call_payloads[1]["contents"][2][
        "parts"
    ][0][
        "text"
    ]
    assert len(result) == 2


def test_second_invalid_response_raises_controlled_error() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return _api_response([])

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            interpreter = GeminiInterpreter(_settings(), client=client)
            await interpreter.interpret(["Relevant note"], 500)

    with pytest.raises(InternalProcessingError):
        asyncio.run(run())
    assert call_count == 2


load_dotenv()
_LIVE_KEY = os.getenv("GEMINI_API_KEY", "").strip()
_PLACEHOLDER_KEYS = {
    "",
    "test-only-key",
    "your-api-key",
    "your_real_key_here",
    "paste_your_real_key_here",
}
_HAS_REAL_KEY = (
    len(_LIVE_KEY) >= 20 and _LIVE_KEY.lower() not in _PLACEHOLDER_KEYS
)


@pytest.mark.live
@pytest.mark.skipif(not _HAS_REAL_KEY, reason="real-looking GEMINI_API_KEY not set")
def test_live_published_examples() -> None:
    get_settings.cache_clear()
    interpreter = GeminiInterpreter(get_settings())
    notes = [
        "Solar output will drop to about 20% from 1 PM to 3 PM.",
        "Do not charge the battery between 2 PM and 4 PM.",
    ]

    result = asyncio.run(interpreter.interpret(notes, battery_capacity_kwh=500))

    assert result[0].directive_type == "solar_reduction"
    assert result[0].structured_adjustment == {"hours": [13, 14], "factor": 0.2}
    assert result[1].directive_type == "no_charge_window"
    assert result[1].structured_adjustment == {"hours": [14, 15]}
