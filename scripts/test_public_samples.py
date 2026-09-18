"""Run all organizer public samples through the live API (spec.md section 15.2)."""

from argparse import ArgumentParser
import json
from pathlib import Path
import sys
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.replay import ReplayValidationError, validate_replay
from app.schemas import OptimizeRequest, OptimizeResponse


REFERENCE_DIR = PROJECT_ROOT / "reference"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _sample_file() -> Path:
    matches = sorted(REFERENCE_DIR.glob("*.json"))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one public sample JSON file, found {len(matches)}."
        )
    return matches[0]


def _load_cases() -> list[dict[str, Any]]:
    payload = json.loads(_sample_file().read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list):
        raise RuntimeError("Public sample JSON must contain a cases list.")
    return cases


def run(base_url: str) -> list[dict[str, Any]]:
    """POST every public input and independently verify each returned response."""

    results: list[dict[str, Any]] = []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30.0) as client:
        for case in _load_cases():
            response = client.post("/optimize-energy", json=case["input"])
            body = response.json()
            result = {
                "case_id": case["id"],
                "label": case.get("label", ""),
                "reference_total_cost_bdt": case["expected_output"][
                    "total_cost_bdt"
                ],
            }
            if response.is_success:
                request_model = OptimizeRequest.model_validate(case["input"])
                response_model = OptimizeResponse.model_validate(body)
                try:
                    validate_replay(request_model, response_model)
                except ReplayValidationError as exc:
                    message = str(exc)
                    result["replay_passed"] = False
                    result["directive_violated"] = any(
                        marker in message
                        for marker in (
                            "directive",
                            "no-charge",
                            "no-discharge",
                            "grid-cap",
                            "solar-reduction",
                        )
                    )
                    result["replay_error"] = message
                else:
                    result["replay_passed"] = True
                    result["directive_violated"] = False
                result["returned_total_cost_bdt"] = response_model.total_cost_bdt
                result["cost_delta_bdt"] = round(
                    response_model.total_cost_bdt
                    - case["expected_output"]["total_cost_bdt"],
                    6,
                )
            else:
                result["replay_passed"] = False
                result["directive_violated"] = "not evaluated"
                result["error"] = {
                    "http_status": response.status_code,
                    "body": body,
                }
            results.append(result)
    return results


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    results = run(args.base_url)
    print(
        "| Case | Replay | Returned cost (BDT) | Reference cost (BDT) | "
        "Delta (BDT) | Directive violated |"
    )
    print("|---|---:|---:|---:|---:|---:|")
    for result in results:
        returned = result.get("returned_total_cost_bdt", "-")
        delta = result.get("cost_delta_bdt", "-")
        print(
            f"| {result['case_id']} | {result['replay_passed']} | {returned} | "
            f"{result['reference_total_cost_bdt']} | {delta} | "
            f"{result['directive_violated']} |"
        )


if __name__ == "__main__":
    main()
