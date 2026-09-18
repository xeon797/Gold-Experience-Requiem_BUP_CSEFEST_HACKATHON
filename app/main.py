"""FastAPI entry point for the GridWise pipeline in spec.md section 5."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from math import fsum
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.directives import compile_directives
from app.errors import InternalProcessingError, register_exception_handlers
from app.interpreter import GeminiInterpreter
from app.optimizer import SolverHour, solve_energy_plan
from app.replay import ReplayValidationError, validate_replay
from app.schemas import (
    DirectiveInterpretation,
    HourlyPlanEntry,
    OptimizeRequest,
    OptimizeResponse,
)
from app.summary import build_plan_summary


logger = logging.getLogger(__name__)
OUTPUT_PRECISION = 6
ACTION_EPSILON = 1e-7

SWAGGER_CUSTOM_HEAD = """
<link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-white: #ffffff;
    --dark-raspberry: #85144b;
    --dark-raspberry-hover: #6d103d;
    --dark-raspberry-subtle: #fdf0f5;
    --navy-electric: #0b1e4f;
    --navy-electric-bright: #0047ff;
    --navy-electric-subtle: #eef3ff;
    --text-main: #1e293b;
    --text-muted: #64748b;
  }

  body, .swagger-ui {
    background-color: var(--bg-white) !important;
    font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    color: var(--text-main) !important;
  }

  .swagger-ui .topbar {
    background-color: var(--navy-electric) !important;
    border-bottom: 3px solid var(--dark-raspberry) !important;
    padding: 12px 0 !important;
  }

  .swagger-ui .topbar .topbar-wrapper .link {
    font-family: 'Satoshi', sans-serif !important;
    font-weight: 700 !important;
  }

  .swagger-ui .info .title {
    font-family: 'Satoshi', sans-serif !important;
    font-weight: 700 !important;
    color: var(--navy-electric) !important;
  }

  .swagger-ui .info .title small.version-stamp {
    background-color: var(--dark-raspberry) !important;
  }

  .swagger-ui .info p, .swagger-ui .info li {
    font-family: 'Satoshi', sans-serif !important;
  }

  /* GET Endpoint styling */
  .swagger-ui .opblock.opblock-get {
    border-color: var(--navy-electric-bright) !important;
    background: var(--navy-electric-subtle) !important;
    border-radius: 8px !important;
  }

  .swagger-ui .opblock.opblock-get .opblock-summary-method {
    background: var(--navy-electric-bright) !important;
    font-family: 'Satoshi', sans-serif !important;
    font-weight: 700 !important;
    border-radius: 4px !important;
  }

  .swagger-ui .opblock.opblock-get .opblock-summary-path {
    font-family: 'Satoshi', sans-serif !important;
    color: var(--navy-electric) !important;
    font-weight: 600 !important;
  }

  /* POST Endpoint styling */
  .swagger-ui .opblock.opblock-post {
    border-color: var(--dark-raspberry) !important;
    background: var(--dark-raspberry-subtle) !important;
    border-radius: 8px !important;
  }

  .swagger-ui .opblock.opblock-post .opblock-summary-method {
    background: var(--dark-raspberry) !important;
    font-family: 'Satoshi', sans-serif !important;
    font-weight: 700 !important;
    border-radius: 4px !important;
  }

  .swagger-ui .opblock.opblock-post .opblock-summary-path {
    font-family: 'Satoshi', sans-serif !important;
    color: var(--dark-raspberry) !important;
    font-weight: 600 !important;
  }

  /* Execute and Try-out Buttons */
  .swagger-ui .btn.execute {
    background-color: var(--dark-raspberry) !important;
    border-color: var(--dark-raspberry) !important;
    color: #ffffff !important;
    font-family: 'Satoshi', sans-serif !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
    box-shadow: 0 2px 4px rgba(133, 20, 75, 0.25) !important;
    transition: all 0.2s ease !important;
  }

  .swagger-ui .btn.execute:hover {
    background-color: var(--dark-raspberry-hover) !important;
    border-color: var(--dark-raspberry-hover) !important;
    box-shadow: 0 4px 8px rgba(133, 20, 75, 0.35) !important;
  }

  .swagger-ui .btn.try-out__btn {
    border-color: var(--navy-electric-bright) !important;
    color: var(--navy-electric-bright) !important;
    font-family: 'Satoshi', sans-serif !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
    transition: all 0.2s ease !important;
  }

  .swagger-ui .btn.try-out__btn:hover {
    background-color: var(--navy-electric-subtle) !important;
  }

  .swagger-ui section.models {
    border-color: #e2e8f0 !important;
    border-radius: 8px !important;
  }

  .swagger-ui section.models.is-open h4 {
    border-bottom-color: #e2e8f0 !important;
    color: var(--navy-electric) !important;
    font-family: 'Satoshi', sans-serif !important;
    font-weight: 700 !important;
  }
</style>
</head>
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Validate required configuration when the application starts."""

    app.state.settings = get_settings()
    yield


app = FastAPI(title="GridWise LLM", lifespan=lifespan, docs_url=None)
register_exception_handlers(app)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect root requests to the interactive API documentation."""

    return RedirectResponse(url="/docs", status_code=307)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html() -> HTMLResponse:
    """Render customized Swagger UI with Satoshi typography and custom palette."""

    base_response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )
    custom_html = base_response.body.decode("utf-8").replace("</head>", SWAGGER_CUSTOM_HEAD)
    return HTMLResponse(content=custom_html)


def get_interpreter(request: Request) -> GeminiInterpreter:
    """Build the request-scoped Gemini interpreter from startup settings."""

    return GeminiInterpreter(request.app.state.settings)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the side-effect-free health response required by section 5.1."""

    return {"status": "ok"}


def _rounded(value: float) -> float:
    rounded = round(float(value), OUTPUT_PRECISION)
    return 0.0 if rounded == 0 else rounded


def construct_response(
    request: OptimizeRequest,
    interpretations: list[DirectiveInterpretation],
    solution: list[SolverHour],
) -> OptimizeResponse:
    """Serialize one canonical solver solution and recompute emitted totals."""

    if len(solution) != 24:
        raise InternalProcessingError("Energy optimization failed.")
    source_hours = {entry.hour: entry for entry in request.hours}
    hourly_plan: list[HourlyPlanEntry] = []
    previous_energy = request.battery.initial_energy_kwh

    for solved in sorted(solution, key=lambda entry: entry.hour):
        energy_after = _rounded(solved.battery_energy_after_kwh)
        signed_change = _rounded(energy_after - previous_energy)
        solar_used = _rounded(solved.solar_used_kwh)
        grid = _rounded(
            source_hours[solved.hour].demand_kwh + signed_change - solar_used
        )
        if grid < 0 and abs(grid) <= 10 ** (-OUTPUT_PRECISION):
            grid = 0.0
        if grid < 0 or solar_used < 0 or energy_after < 0:
            raise InternalProcessingError("Energy optimization failed.")

        if signed_change > ACTION_EPSILON:
            action = "charge"
            battery_kwh = _rounded(signed_change)
        elif signed_change < -ACTION_EPSILON:
            action = "discharge"
            battery_kwh = _rounded(-signed_change)
        else:
            action = "idle"
            battery_kwh = 0.0

        hourly_plan.append(
            HourlyPlanEntry(
                hour=solved.hour,
                grid_kwh=grid,
                solar_used_kwh=solar_used,
                battery_action=action,
                battery_kwh=battery_kwh,
                battery_energy_after_kwh=energy_after,
            )
        )
        previous_energy = energy_after

    total_grid = _rounded(fsum(entry.grid_kwh for entry in hourly_plan))
    total_cost = _rounded(
        fsum(
            entry.grid_kwh
            * source_hours[entry.hour].tariff_bdt_per_kwh
            for entry in hourly_plan
        )
    )
    peak_grid = _rounded(max(entry.grid_kwh for entry in hourly_plan))
    return OptimizeResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=interpretations,
        hourly_plan=hourly_plan,
        total_grid_kwh=total_grid,
        total_cost_bdt=total_cost,
        peak_grid_kwh=peak_grid,
        plan_summary=build_plan_summary(
            interpretations,
            total_grid,
            total_cost,
            peak_grid,
        ),
    )


@app.post("/optimize-energy", response_model=OptimizeResponse, status_code=200)
async def optimize_energy(
    request: OptimizeRequest,
    interpreter: Annotated[GeminiInterpreter, Depends(get_interpreter)],
) -> OptimizeResponse:
    """Interpret, compile, optimize, serialize, replay, and return one plan."""

    directive_interpretation = await interpreter.interpret(
        request.operator_notes,
        battery_capacity_kwh=request.battery.capacity_kwh,
    )
    compiled = compile_directives(request, directive_interpretation)
    solution = solve_energy_plan(request, compiled)
    response = construct_response(request, directive_interpretation, solution)
    try:
        validate_replay(request, response)
    except ReplayValidationError as exc:
        logger.exception("Independent response replay failed: %s", exc)
        raise InternalProcessingError() from exc
    return response
