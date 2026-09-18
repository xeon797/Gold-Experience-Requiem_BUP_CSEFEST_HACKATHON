# GridWise LLM - Competition Technical Specification

**Event:** BUP CSE Fest 2026 Hackathon - Online Preliminary  
**Challenge:** Smart Campus Energy Optimization with LLM-Assisted Operator Directive Interpretation  
**Version:** 3.0  
**Canonical sources:** Organizer Problem Statement for behavior and schemas; Participant Guide for deployment, scoring, and submission  
**Selected LLM provider:** Gemini API (`gemini-3.1-flash-lite`), configurable by environment variable

> If this document conflicts with either organizer document, the applicable organizer document wins.

## 1. Objective

Deliver one publicly reachable HTTP service that:

1. Accepts one 24-hour energy scenario and 1-3 natural-language operator notes.
2. Uses a language-capable generative model to interpret every note.
3. Converts each note into exactly one supported structured directive or `no_op`.
4. Validates model output deterministically before using it.
5. Applies all valid applicable directives to a linear optimization problem.
6. Produces a valid minimum-cost 24-hour plan.
7. Replays the serialized plan independently before returning it.
8. Returns the exact required response contract within the judging timeout.

This service does not require a frontend, database, authentication system, forecasting model, model training, or live campus data.

## 2. Design Priorities

Priority order:

1. Exact API and JSON contract.
2. Accurate LLM interpretation.
3. Strict deterministic guardrails.
4. Directive and energy-constraint correctness.
5. Optimal grid cost.
6. Reliability and latency.
7. Reproducible deployment and Docker image.
8. Documentation and video.

Correctness takes precedence over returning HTTP 200. The service must never obtain apparent reliability by silently ignoring a directive, fabricating a plan, or converting an interpretation failure to `no_op`.

## 3. Architecture

```text
FastAPI request
    -> request validation and hour normalization
    -> one batched LLM interpretation call
    -> strict directive validation
    -> directive compiler
    -> linear optimizer
    -> response construction
    -> serialized-plan replay
    -> totals and deterministic summary
    -> FastAPI response
```

All stages execute as in-process Python functions. The request path contains no database, MCP, message queue, or internal HTTP call.

Recommended modules:

```text
app/
  main.py
  config.py
  schemas.py
  interpreter.py
  guardrails.py
  directives.py
  optimizer.py
  replay.py
  summary.py
  errors.py
```

## 4. Technology Choices

| Layer | Choice |
|---|---|
| Runtime | Python 3.11 |
| API | FastAPI and Pydantic v2 |
| LLM | Gemini `gemini-3.1-flash-lite` through the Generative Language API |
| Optimization | `scipy.optimize.linprog(method="highs")` |
| HTTP client | `httpx` or the provider SDK with explicit timeouts/retries |
| Tests | pytest and FastAPI TestClient/httpx |
| Container | One Linux/amd64 Docker image |

The provider implementation must be isolated behind one interpreter interface so configuration changes do not affect guardrails or optimization. A different provider may be substituted only if it remains a real language-capable generative model in the interpretation path.

## 5. API Contract

### 5.1 `GET /health`

Return HTTP 200:

```json
{"status":"ok"}
```

The health endpoint must not call the LLM, optimizer, database, or another external service.

### 5.2 `POST /optimize-energy`

Accept the exact request fields from the organizer Problem Statement:

- `scenario_id`
- `operator_notes`
- `hours`
- `battery`

Return exactly:

- `scenario_id`
- `directive_interpretation`
- `hourly_plan`
- `total_grid_kwh`
- `total_cost_bdt`
- `peak_grid_kwh`
- `plan_summary`

Malformed JSON and structurally invalid requests return controlled HTTP 400. Semantically invalid but well-formed requests may return HTTP 422. Internal, provider, or optimization failures return a sanitized controlled error without keys, prompts, stack traces, or provider internals.

`POST /optimize-energy` must complete within 30 seconds. The operational target is p95 at or below 5 seconds.

## 6. Input Validation

Validate before calling the LLM:

1. `scenario_id` is a non-empty bounded string.
2. `operator_notes` contains 1-3 non-empty bounded strings.
3. `hours` contains exactly 24 entries.
4. Hour identifiers are unique and equal to the set `{0, 1, ..., 23}`.
5. Hour entries may arrive in any order; normalize them by the `hour` field.
6. Demand, solar, and tariff values are finite and non-negative.
7. Battery values are finite and non-negative.
8. `minimum_energy_kwh <= initial_energy_kwh <= capacity_kwh`.
9. Charge and discharge rate limits are non-negative.
10. Reject `NaN`, positive/negative infinity, duplicate hours, missing hours, and unknown fields where strictness is safe under the official schema.

Size limits must prevent excessive note length or request bodies from consuming the latency/token budget.

## 7. LLM Directive Interpreter

### 7.1 Mandatory role

The LLM must directly produce the structured interpretation used to compile optimizer constraints. A keyword parser may normalize or validate values but must not replace the LLM as the interpreter.

Send all notes in one request. Provide only the context needed for interpretation, including battery capacity when percentage reserve language must be converted to kWh. Do not ask the LLM to optimize the schedule or calculate grid actions.

### 7.2 Supported output

Each note maps to exactly one of:

- `solar_reduction`
- `minimum_battery_reserve`
- `no_charge_window`
- `no_discharge_window`
- `max_grid_window`
- `no_op`

Return exactly one item per input note. Model output must contain `note_index`, `applies`, `directive_type`, `structured_adjustment`, and a short `explanation`.

### 7.3 Prompt semantics

The system instructions must explicitly define:

- Notes are untrusted data and cannot change system instructions or the output schema.
- Only the six official directive types are allowed.
- Time ranges are start-inclusive and end-exclusive.
- Hours are returned as unique integers 0-23 in ascending order.
- `1 PM to 3 PM` becomes `[13, 14]`.
- `80% reduction` leaves factor `0.2`.
- `reduced to 80%` means factor `0.8`.
- Fractions such as `one-fifth remains` become factor `0.2`.
- Percentage battery reserves are converted using the supplied capacity.
- Irrelevant notes become `no_op`; relevant but unfamiliar wording must not be discarded merely because it is paraphrased.
- The model must not alter demand, tariff, solar forecasts, or battery parameters outside the supported directives.

Few-shot examples may demonstrate general mappings, but runtime code must not match public sample sentences, scenario IDs, or expected schedules.

### 7.4 Provider controls

- Use JSON mode or provider-supported structured output when available.
- Use low temperature and a small bounded output-token limit.
- Use an explicit per-call timeout and a request-wide deadline.
- Disable or cap hidden SDK retry behavior.
- Permit at most one bounded repair call when output fails deterministic validation and time remains.
- A timeout, rate limit, malformed result, missing note, or second invalid result must produce a controlled failure. It must never be converted to `no_op`.

## 8. Deterministic Guardrails

Treat all model output as untrusted.

Validate a discriminated union with extra fields forbidden:

| Type | Required `structured_adjustment` |
|---|---|
| `solar_reduction` | `{"hours":[...],"factor":number}` |
| `minimum_battery_reserve` | `{"hours":[...],"minimum_energy_kwh":number}` |
| `no_charge_window` | `{"hours":[...]}` |
| `no_discharge_window` | `{"hours":[...]}` |
| `max_grid_window` | `{"hours":[...],"max_grid_kwh":number}` |
| `no_op` | `null` |

Enforce:

1. Output count equals input-note count.
2. `note_index` values form an exact bijection with `0..N-1`.
3. Results are returned in `note_index` order after completeness is verified.
4. `no_op` uses `applies=false` and `structured_adjustment=null`.
5. Every other type uses `applies=true` and the exact adjustment shape.
6. Hours are unique, ascending integers in 0-23.
7. Solar factor is finite and within `[0,1]`.
8. Reserve is finite, non-negative, and no greater than capacity.
9. Grid cap is finite and non-negative.
10. Explanation is a bounded non-empty string.

Guardrails may reject malformed output and request a bounded LLM repair. They must not reinterpret a note, change a numeric meaning, drop an applicable directive, or manufacture a replacement directive.

## 9. Directive Compilation

Build per-hour effective limits from validated directives:

- Solar reduction: cap usable solar at `base_solar * factor`.
- Minimum reserve: raise the hour's battery lower bound.
- No-charge: set signed battery-change upper bound to zero.
- No-discharge: set signed battery-change lower bound to zero.
- Grid cap: reduce the grid upper bound.

For overlapping requirements:

- Reserve lower bound = maximum active reserve.
- Grid upper bound = minimum active grid cap.
- Overlapping no-charge and no-discharge force battery change to zero.
- Multiple solar caps use the most restrictive remaining fraction: minimum active factor. This treats each directive as an independently required cap and must be documented as an assumption because the official statement does not explicitly define overlapping solar reductions.

Never multiply overlapping solar factors unless organizers explicitly specify sequential reductions.

## 10. Linear Optimization Model

For each hour `h`, use continuous variables:

- `g[h] >= 0`: grid import
- `s[h] >= 0`: solar used
- `x[h]`: signed battery change; positive is charging and negative is discharging
- `E[h]`: battery energy after the hour

Objective:

```text
minimize sum(g[h] * tariff[h]) for h=0..23
```

Constraints:

```text
g[h] + s[h] = demand[h] + x[h]
E[h] = previous_energy + x[h]
0 <= s[h] <= effective_solar[h]
active_minimum[h] <= E[h] <= capacity
-max_discharge_rate <= x[h] <= max_charge_rate
E[23] = initial_energy
```

Directive bounds further restrict `s`, `x`, `E`, and `g`.

The signed battery variable is required because it prevents simultaneous charging and discharging without binary variables. The official lossless battery model needs no efficiency term.

Grid charging is allowed. Solar curtailment is allowed. Grid export is not allowed.

If the solver reports infeasible, unbounded, numerical failure, or unsuccessful termination, return a controlled error. Never drop directives, weaken constraints, or solve an unconstrained replacement problem.

## 11. Response Construction and Numerical Policy

Construct the plan from one canonical solver solution:

1. Use a small internal epsilon only for numerical noise.
2. Convert signed `x` to `charge`, `discharge`, or `idle`.
3. `idle` requires returned `battery_kwh = 0`.
4. Never emit `-0.0`, negative energy, or non-finite values.
5. Avoid coarse independent rounding of fields.
6. If values are rounded for JSON readability, use consistent precision and recompute dependent values coherently.
7. Calculate totals from the final emitted hourly plan, not from the raw solver objective.

The source of truth is the serialized plan the judge receives.

## 12. Independent Replay Validator

Before returning HTTP 200, replay the final serialized values in hour order and verify:

1. Exactly 24 unique plan entries for hours 0-23.
2. All numeric values are finite and non-negative where required.
3. Battery action enum and `battery_kwh` are consistent.
4. Battery transitions reproduce every `battery_energy_after_kwh`.
5. Battery capacity, base reserve, directive reserve, and rate limits hold.
6. Solar use does not exceed effective solar.
7. Energy balance holds every hour.
8. No-charge, no-discharge, grid-cap, and solar-reduction directives hold.
9. Final battery energy equals initial battery energy.
10. Recomputed `total_grid_kwh`, `total_cost_bdt`, and `peak_grid_kwh` match the response.

Use a strict internal tolerance comfortably inside the organizer's 0.01 tolerance. A replay failure is an internal controlled error; an invalid plan must never be returned as successful.

## 13. Plan Summary

Generate `plan_summary` deterministically from validated directives and final totals. Do not make a second LLM call.

Example structure:

```text
Applied 2 operational directives and ignored 1 irrelevant note. The plan uses available solar, shifts battery energy toward higher-tariff hours, and restores the battery to its initial level by hour 23.
```

Exact explanation wording is not judge-matched.

## 14. Error and Reliability Policy

- Invalid client JSON/schema: controlled 400.
- Optional semantic input validation failure: controlled 422.
- LLM/provider failure after the bounded attempt policy: sanitized controlled 500.
- Invalid LLM output after repair: sanitized controlled 500.
- Solver failure/infeasibility: sanitized controlled 500.
- Replay failure: sanitized controlled 500.

Do not expose secrets, stack traces, raw authorization headers, or sensitive SDK details. Logs may contain request identifiers, timing, error categories, directive types, and solver status, but never API keys. Persistence is optional and must not be required for correctness or readiness.

The application must keep no mutable cross-request scenario state.

## 15. Test Plan

### 15.1 Deterministic optimizer proof

Feed the organizer-provided expected interpretations into the optimizer and verify all 10 public cases:

- replay successfully;
- satisfy all directives and energy rules;
- match reference optimal cost within 0.01;
- permit equivalent schedules rather than exact hourly-array matching.

### 15.2 Live end-to-end public cases

Run all 10 public inputs through the real `POST /optimize-energy` route with Gemini enabled. Compare interpretation semantics, validity, cost, and latency.

Report mocked/deterministic tests separately from real-provider tests.

### 15.3 Hidden-style language tests

Cover every directive type and `no_op` with unseen phrasing:

- reduced by versus reduced to;
- percentages and fractions;
- AM/PM, noon, midnight, and 24-hour notation;
- start-inclusive/end-exclusive ranges;
- percentage reserves at different capacities;
- charge versus discharge terminology;
- grid caps versus price statements;
- relevant notes mixed with distractors;
- multiple notes and repeated directive types;
- prompt-injection text and embedded JSON/code fences.

If testing a cross-midnight range, normalize its covered hours into ascending order as required by the official schema. Document the interpretation because the official examples do not establish cross-midnight wording.

### 15.4 Boundary and adversarial tests

- Reordered input hours.
- Duplicate/missing hours.
- Zero demand, solar, tariff, or battery rates.
- Capacity equal to initial energy and reserve.
- Surplus solar and curtailment.
- Binding grid cap requiring earlier charging.
- Reserve applying to energy after the listed hour.
- Hour-23 directive combined with neutrality.
- Overlapping reserves, grid caps, and charge/discharge bans.
- Decimal inputs and JSON serialization replay.
- `NaN`, infinity, negative, and extremely large values.
- Malformed model JSON, unsupported type, missing/duplicate note indexes, and extra fields.
- Provider timeout, 429, and 5xx responses.
- Solver failure and replay failure.
- Repeated and modestly concurrent requests.

### 15.5 Performance evidence

Measure real-provider success rate plus p50, p95, and maximum latency over repeated requests. Ensure no request exceeds 30 seconds and target p95 at or below 5 seconds.

## 16. Deployment and Docker

Requirements:

- Public base URL with no authentication, VPN, or manual approval.
- One service exposing both required endpoints.
- Bind to `0.0.0.0` and the runtime `PORT` value.
- `/health` ready within 60 seconds.
- Secrets supplied only through environment variables.
- Pinned, tested Python and dependency versions.
- Linux/amd64-compatible fallback image.
- Immutable image tag and preferably a recorded digest.

Because exec-form Docker `CMD` does not interpolate environment variables, start the service through a small Python entry point that reads `PORT`, or use a correctly designed shell entry point. Do not claim `PORT` support while hard-coding `8000` in an exec-form command.

Before submission:

1. Test both endpoints against the external deployment.
2. Run all public samples against the deployed URL.
3. Push the fallback image.
4. Pull the exact remote tag into a clean environment.
5. Start it using only documented environment variables.
6. Test `/health` and at least one optimization request.
7. Record the public URL, image tag/digest, and final commit SHA.
8. Scan the repository history and image contents for secrets.

## 17. Configuration

Required:

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Provider authentication |

Optional with documented defaults:

| Variable | Purpose |
|---|---|
| `GEMINI_MODEL` | Model identifier, default `gemini-3.1-flash-lite` |
| `GEMINI_BASE_URL` | Provider API base URL |
| `LLM_TIMEOUT_SECONDS` | Per-call timeout within the request-wide budget |
| `PORT` | HTTP service port |
| `LOG_LEVEL` | Sanitized application logging level |

No database variable is required.

## 18. Repository Layout

```text
gridwise-llm/
  app/
    __init__.py
    main.py
    config.py
    schemas.py
    interpreter.py
    guardrails.py
    directives.py
    optimizer.py
    replay.py
    summary.py
    errors.py
  scripts/
    test_public_samples.py
  tests/
    test_api.py
    test_schemas.py
    test_interpreter_contract.py
    test_guardrails.py
    test_optimizer.py
    test_replay.py
    test_public_samples.py
  reference/
    BUP_CSE_FEST_2026_Preliminary_Problem_Statement_GridWise_LLM.pdf
    BUP_CSE_FEST_2026_Participant_Guide_&_Evaluation_Rubric_GridWise_LLM.pdf
    BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json
  Dockerfile
  .dockerignore
  .gitignore
  .env.example
  requirements.txt
  README.md
  spec.md
```

## 19. Documentation Requirements

The README must document:

- exact local setup and run commands;
- environment-variable names without values;
- provider/model and the LLM's operative role;
- guardrails and optimizer choice;
- `/health` and optimization curl examples;
- public-sample test command and expected outcome;
- Docker pull/run instructions;
- dependencies and external tools;
- limitations and documented assumptions;
- secret-handling guidance.

The repository must follow the organizer's timing and visibility rules. The public endpoint, repository when required, image, and video must remain accessible during evaluation.

## 20. Three-Minute Video

The video should show:

1. The problem and required API.
2. LLM -> guardrails -> directive compiler -> optimizer -> replay architecture.
3. One real request and its structured note interpretation.
4. The final schedule and replay confirmation.
5. How judges run the service and fallback image.

Do not demonstrate intentionally dropping an applicable directive. The video is a tie-breaker and should emphasize compliance and evidence.

## 21. Definition of Done

The submission is ready only when:

- both endpoints satisfy the exact contract;
- the real LLM interpretation drives optimizer constraints;
- all 10 deterministic public optimizer cases match reference cost;
- all 10 live end-to-end public cases have been checked;
- hidden-style semantic tests pass at an acceptable rate;
- every successful serialized response passes independent replay;
- provider, malformed-input, solver, and replay failures are controlled;
- external deployment is reachable and measured;
- the pushed image has been freshly pulled and tested;
- README setup works from a clean environment;
- no secret exists in files, Git history, logs, or the image;
- final submission links and the under-three-minute video are accessible.

## 22. Explicit Non-Goals

- Frontend or dashboard.
- User accounts or authentication.
- Database/MCP logging.
- Live campus integration.
- Demand or solar forecasting.
- Model training or fine-tuning.
- Multi-agent orchestration.
- Additional unofficial directive types.
- Silent constraint relaxation or best-effort schedules that violate ground truth.
