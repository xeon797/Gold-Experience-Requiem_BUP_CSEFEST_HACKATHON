"""Deterministic plan summaries from spec.md section 13."""

from app.schemas import DirectiveInterpretation


def build_plan_summary(
    interpretations: list[DirectiveInterpretation],
    total_grid_kwh: float,
    total_cost_bdt: float,
    peak_grid_kwh: float,
) -> str:
    """Describe applied directives and final totals without another LLM call."""

    applied = [item for item in interpretations if item.applies]
    ignored = len(interpretations) - len(applied)
    directive_types = list(dict.fromkeys(item.directive_type for item in applied))
    if directive_types:
        controls = ", ".join(name.replace("_", " ") for name in directive_types)
        control_text = f" Applied controls: {controls}."
    else:
        control_text = ""
    return (
        f"Applied {len(applied)} operational directive(s) and ignored {ignored} "
        f"irrelevant note(s).{control_text} Grid use is {total_grid_kwh:.2f} kWh, "
        f"cost is {total_cost_bdt:.2f} BDT, and peak grid use is "
        f"{peak_grid_kwh:.2f} kWh; the battery returns to its initial energy."
    )
