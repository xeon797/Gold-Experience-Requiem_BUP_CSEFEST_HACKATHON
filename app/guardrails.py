"""Pure deterministic validation of model output from spec.md section 8."""

from math import isfinite
from typing import Any

from app.schemas import DirectiveInterpretation


MAX_EXPLANATION_LENGTH = 500
ITEM_KEYS = {
    "note_index",
    "applies",
    "directive_type",
    "structured_adjustment",
    "explanation",
}
ADJUSTMENT_KEYS = {
    "solar_reduction": {"hours", "factor"},
    "minimum_battery_reserve": {"hours", "minimum_energy_kwh"},
    "no_charge_window": {"hours"},
    "no_discharge_window": {"hours"},
    "max_grid_window": {"hours", "max_grid_kwh"},
}
ALLOWED_DIRECTIVE_TYPES = {*ADJUSTMENT_KEYS, "no_op"}


class GuardrailValidationError(ValueError):
    """Raised when untrusted LLM output violates the directive contract."""


def _is_json_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _require_finite_number(value: object, field_name: str) -> float:
    if not _is_json_number(value) or not isfinite(value):
        raise GuardrailValidationError(f"{field_name} must be a finite number")
    return float(value)


def _validate_hours(value: object, note_index: int) -> list[int]:
    if not isinstance(value, list) or not value:
        raise GuardrailValidationError(
            f"note_index {note_index} hours must be a non-empty array"
        )
    if any(isinstance(hour, bool) or not isinstance(hour, int) for hour in value):
        raise GuardrailValidationError(
            f"note_index {note_index} hours must contain only integers"
        )
    if any(hour < 0 or hour > 23 for hour in value):
        raise GuardrailValidationError(
            f"note_index {note_index} hours must be within 0 through 23"
        )
    if value != sorted(value) or len(value) != len(set(value)):
        raise GuardrailValidationError(
            f"note_index {note_index} hours must be unique and ascending"
        )
    return value


def _validate_adjustment(
    directive_type: str,
    adjustment: object,
    note_index: int,
    battery_capacity_kwh: float,
) -> None:
    if not isinstance(adjustment, dict):
        raise GuardrailValidationError(
            f"note_index {note_index} structured_adjustment must be an object"
        )
    expected_keys = ADJUSTMENT_KEYS[directive_type]
    if set(adjustment) != expected_keys:
        raise GuardrailValidationError(
            f"note_index {note_index} structured_adjustment must contain exact keys "
            f"{sorted(expected_keys)}"
        )

    _validate_hours(adjustment["hours"], note_index)

    if directive_type == "solar_reduction":
        factor = _require_finite_number(adjustment["factor"], "factor")
        if not 0 <= factor <= 1:
            raise GuardrailValidationError("factor must be between 0 and 1 inclusive")
    elif directive_type == "minimum_battery_reserve":
        reserve = _require_finite_number(
            adjustment["minimum_energy_kwh"], "minimum_energy_kwh"
        )
        if reserve < 0:
            raise GuardrailValidationError(
                "minimum_energy_kwh must be non-negative"
            )
        if reserve > battery_capacity_kwh:
            raise GuardrailValidationError(
                "minimum_energy_kwh must not exceed battery capacity"
            )
    elif directive_type == "max_grid_window":
        grid_cap = _require_finite_number(adjustment["max_grid_kwh"], "max_grid_kwh")
        if grid_cap < 0:
            raise GuardrailValidationError("max_grid_kwh must be non-negative")


def validate_interpretations(
    raw_output: object,
    expected_count: int,
    battery_capacity_kwh: float,
) -> list[DirectiveInterpretation]:
    """Validate untrusted parsed JSON and return entries in note-index order."""

    capacity = _require_finite_number(battery_capacity_kwh, "battery capacity")
    if capacity < 0:
        raise GuardrailValidationError("battery capacity must be non-negative")
    if not isinstance(raw_output, list):
        raise GuardrailValidationError("model output must be a JSON array")
    if len(raw_output) != expected_count:
        raise GuardrailValidationError(
            f"model output must contain exactly {expected_count} items"
        )

    validated_items: list[DirectiveInterpretation] = []
    indexes: list[int] = []
    for position, item in enumerate(raw_output):
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            raise GuardrailValidationError(
                f"item {position} must contain the exact fields {sorted(ITEM_KEYS)}"
            )

        note_index = item["note_index"]
        if isinstance(note_index, bool) or not isinstance(note_index, int):
            raise GuardrailValidationError("note_index must be an integer")
        indexes.append(note_index)

        applies = item["applies"]
        if not isinstance(applies, bool):
            raise GuardrailValidationError(
                f"note_index {note_index} applies must be a boolean"
            )

        directive_type = item["directive_type"]
        if directive_type not in ALLOWED_DIRECTIVE_TYPES:
            raise GuardrailValidationError(
                f"note_index {note_index} has an unsupported directive_type"
            )

        explanation = item["explanation"]
        if (
            not isinstance(explanation, str)
            or not explanation.strip()
            or len(explanation) > MAX_EXPLANATION_LENGTH
        ):
            raise GuardrailValidationError(
                f"note_index {note_index} explanation must be non-empty and at most "
                f"{MAX_EXPLANATION_LENGTH} characters"
            )

        adjustment = item["structured_adjustment"]
        if directive_type == "no_op":
            if applies is not False or adjustment is not None:
                raise GuardrailValidationError(
                    "no_op requires applies=false and structured_adjustment=null"
                )
        else:
            if applies is not True:
                raise GuardrailValidationError(
                    f"directive_type {directive_type} requires applies=true"
                )
            _validate_adjustment(
                directive_type,
                adjustment,
                note_index,
                capacity,
            )

        validated_items.append(DirectiveInterpretation.model_validate(item))

    if sorted(indexes) != list(range(expected_count)):
        raise GuardrailValidationError(
            "note_index values must form an exact bijection with the input notes"
        )

    return sorted(validated_items, key=lambda item: item.note_index)
