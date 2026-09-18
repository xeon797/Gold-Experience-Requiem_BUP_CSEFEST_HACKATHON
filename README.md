# GridWise LLM

Smart Campus Energy Optimization Service with LLM-Assisted Operator Directive Interpretation.

---

## 1. Problem Summary and Architecture

GridWise LLM is an energy optimization service designed for the BUP CSE Fest 2026 Hackathon. It accepts a 24-hour campus energy profile (hourly demand, solar generation forecast, and time-of-use tariff rates) alongside 1 to 3 natural-language operator notes. The service interprets the unstructured operational directives using a large language model, deterministically validates and compiles the directives into mathematical constraints, solves for the global minimum grid electricity cost using linear programming, independently replays and verifies all 10 problem constraints, and serializes the optimal hourly schedule with zero manual intervention.

### Pipeline Flow
```text
FastAPI Request
   │
   ▼
Request Validation & Hour Normalization (Pydantic v2)
   │
   ▼
LLM Interpretation (Google Gemini gemini-3.1-flash-lite via JSON Schema)
   │
   ▼
Strict Guardrail Validation (Deterministic 0..N-1 bijection, ascending hours, bounds)
   │
   ▼
Directive Compiler (Deterministic bounds, minimum solar factor, maximum reserve)
   │
   ▼
Linear Optimizer (scipy.optimize.linprog with HiGHS simplex/interior-point solver)
   │
   ▼
Response Construction (Hourly battery action, grid import, and solar usage)
   │
   ▼
Independent Plan Replay (Deterministic validation of all 10 physical & directive constraints)
   │
   ▼
FastAPI Response (HTTP 200 with optimal schedule and deterministic summary)
```

All pipeline stages execute in-process. The request path contains no database, external cache, message queue, or background workers.

---

## 2. Environment Variables

All settings are configured via environment variables. Sensitive keys are never hardcoded.

| Variable | Requirement | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | **Required** | *None* | Google Gemini API key used for directive interpretation. |
| `GEMINI_MODEL` | Optional | `gemini-3.1-flash-lite` | Gemini model name. |
| `GEMINI_BASE_URL` | Optional | `https://generativelanguage.googleapis.com/v1beta` | Base URL for Google Generative Language API. |
| `LLM_TIMEOUT_SECONDS` | Optional | `20.0` | Per-call HTTP timeout for Gemini API calls. |
| `PORT` | Optional | `8000` | HTTP port on which the Uvicorn web server listens. |
| `LOG_LEVEL` | Optional | `INFO` | Sanitized application logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

> **Security Note:** Secrets must never be committed to source control. Supply `GEMINI_API_KEY` only through environment variables or a local `.env` file that is excluded by `.gitignore` and `.dockerignore`.

---

## 3. Model and Division of Responsibility

### Provider & Model
- **Provider:** Google Gemini
- **Model:** `gemini-3.1-flash-lite` (via Generative Language REST API)

### Operative Role of LLM vs. Deterministic Code
- **LLM Role (Stochastic Interpretation):** The language model is used **strictly and exclusively** to interpret unstructured natural-language operator notes into structured directive candidates. It identifies the directive category (`no_op`, `no_charge`, `no_discharge`, `reserve_battery`, `grid_cap`, `solar_reduction`), target hour ranges, and adjustment parameters using strict Gemini JSON schema enforcement.
- **Deterministic Pipeline (Mathematical & Guardrail Logic):**
  - **Input Validation:** Enforces exact Pydantic v2 schemas and valid numeric intervals.
  - **Guardrails:** Deterministically verifies that model output has a strict 1-to-1 bijection with input notes (indexes `0..N-1`), strictly ascending hour lists, and valid parameter ranges.
  - **Directive Compilation:** Resolves multiple overlapping directives into mathematical upper and lower bounds.
  - **Optimization:** Global cost minimization performed mathematically using `scipy.optimize.linprog(method="highs")`.
  - **Replay Validation:** Checks all 10 problem constraints on the serialized output before returning HTTP 200.
  - **Summary Generation:** Deterministically formatted string summarizing total cost, grid usage, and active directives.

---

## 4. Guardrails and Solver

- **Guardrails:** Implemented in `app/guardrails.py`. Rejects malformed JSON, out-of-order hours, missing or duplicated note indexes, invalid directive types, and out-of-bounds parameters. Any non-compliant model output triggers an immediate deterministic validation error.
- **Linear Solver:** Implemented in `app/optimizer.py` using `scipy.optimize.linprog(method="highs")`. Employs the HiGHS dual-simplex and interior-point solver to find the globally optimal energy dispatch across all 24 hours under linear energy balance, battery capacity, maximum charge/discharge rates, end-of-day neutrality, and directive constraints.

---

## 5. Local Quickstart

### Prerequisites
- Python 3.11+ (Python 3.11 recommended for production parity)
- A valid Google Gemini API key

### Clean Clone Setup
```bash
# 1. Clone repository
git clone <REPOSITORY_URL>
cd gridwise-llm

# 2. Create and activate virtual environment
python -m venv .venv

# On Linux / macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# 3. Install pinned dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set:
# GEMINI_API_KEY=your_actual_gemini_api_key_here

# 5. Start the service
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Health Check Verification
In another terminal:
```bash
curl -s http://localhost:8000/health
```

Expected response:
```json
{"status":"ok"}
```

---

## 6. Curl Examples

### 6.1 `GET /health`
```bash
curl -i http://localhost:8000/health
```

**Response:**
```http
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok"}
```

### 6.2 `POST /optimize-energy`
```bash
curl -i -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "SAMPLE-01",
    "operator_notes": [
      "Keep at least 20 kWh in reserve from 6 PM to 10 PM for critical evening campus operations.",
      "Tariff jumps during peak evening hours; battery discharge is encouraged."
    ],
    "hours": [
      {"hour": 0, "demand_kwh": 40.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 1, "demand_kwh": 35.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 2, "demand_kwh": 30.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 3, "demand_kwh": 30.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 4, "demand_kwh": 32.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 5, "demand_kwh": 38.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 6, "demand_kwh": 50.0, "solar_kwh": 5.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 7, "demand_kwh": 70.0, "solar_kwh": 15.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 8, "demand_kwh": 95.0, "solar_kwh": 30.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 9, "demand_kwh": 120.0, "solar_kwh": 50.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 10, "demand_kwh": 140.0, "solar_kwh": 70.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 11, "demand_kwh": 150.0, "solar_kwh": 80.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 12, "demand_kwh": 145.0, "solar_kwh": 85.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 13, "demand_kwh": 140.0, "solar_kwh": 80.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 14, "demand_kwh": 135.0, "solar_kwh": 65.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 15, "demand_kwh": 125.0, "solar_kwh": 45.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 16, "demand_kwh": 110.0, "solar_kwh": 25.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 17, "demand_kwh": 90.0, "solar_kwh": 10.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 18, "demand_kwh": 105.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 19, "demand_kwh": 115.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 20, "demand_kwh": 110.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 21, "demand_kwh": 95.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 22, "demand_kwh": 70.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 23, "demand_kwh": 50.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0}
    ],
    "battery": {
      "capacity_kwh": 100.0,
      "initial_energy_kwh": 30.0,
      "minimum_energy_kwh": 10.0,
      "max_charge_kwh_per_hour": 25.0,
      "max_discharge_kwh_per_hour": 25.0
    }
  }'
```

**Response (HTTP 200):**
```json
{
  "scenario_id": "SAMPLE-01",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "minimum_battery_reserve",
      "structured_adjustment": {
        "hours": [18, 19, 20, 21],
        "minimum_energy_kwh": 20.0
      },
      "explanation": "Reserve at least 20 kWh from 6 PM to 10 PM (hours 18-21)."
    },
    {
      "note_index": 1,
      "applies": false,
      "directive_type": "no_op",
      "structured_adjustment": null,
      "explanation": "General tariff observation; no operational constraint directive."
    }
  ],
  "hourly_plan": [
    {
      "hour": 0,
      "grid_kwh": 40.0,
      "solar_used_kwh": 0.0,
      "battery_action": "idle",
      "battery_kwh": 0.0,
      "battery_energy_after_kwh": 30.0
    }
  ],
  "total_grid_kwh": 1612.0,
  "total_cost_bdt": 38365.0,
  "peak_grid_kwh": 100.0,
  "plan_summary": "Optimal 24-hour schedule formulated with total grid import of 1612.00 kWh, total cost of 38365.00 BDT, and peak grid demand of 100.00 kWh. Applied 1 directive(s): minimum_battery_reserve (hours 18-21)."
}
```

---

## 7. Public Sample Test Execution

Run the public benchmark runner against either the local server or deployed URL:

```bash
# Against local service
python scripts/test_public_samples.py --base-url http://127.0.0.1:8000

# Against deployed service
python scripts/test_public_samples.py --base-url <PUBLIC_URL>
```

### Expected Output
All 10 sample cases pass replay validation with zero directive violations and 0.0 BDT delta matching reference costs exactly:

```text
| Case | Replay | Returned cost (BDT) | Reference cost (BDT) | Delta (BDT) | Directive violated |
|---|---:|---:|---:|---:|---:|
| SAMPLE-01 | True | 38365.0 | 38365 | 0.0 | False |
| SAMPLE-02 | True | 42885.0 | 42885 | 0.0 | False |
| SAMPLE-03 | True | 35480.0 | 35480 | 0.0 | False |
| SAMPLE-04 | True | 40495.0 | 40495 | 0.0 | False |
| SAMPLE-05 | True | 33950.0 | 33950 | 0.0 | False |
| SAMPLE-06 | True | 34090.0 | 34090 | 0.0 | False |
| SAMPLE-07 | True | 38550.0 | 38550 | 0.0 | False |
| SAMPLE-08 | True | 37665.0 | 37665 | 0.0 | False |
| SAMPLE-09 | True | 34873.0 | 34873 | 0.0 | False |
| SAMPLE-10 | True | 41620.0 | 41620 | 0.0 | False |
```

---

## 8. Docker Deployment

### 8.1 Build Locally
```bash
docker build -t gridwise-llm:v1.0.0 .
```

### 8.2 Pull and Run Remote Image
```bash
# Pull remote image
docker pull <REGISTRY>/gridwise-llm:v1.0.0

# Run container binding to local port 8000
docker run -d \
  -p 8000:8000 \
  -e PORT=8000 \
  -e GEMINI_API_KEY="<YOUR_GEMINI_API_KEY>" \
  --name gridwise-service \
  <REGISTRY>/gridwise-llm:v1.0.0
```

Verify container health:
```bash
curl -s http://localhost:8000/health
```

---

## 9. Public Deployment URL

- **Service Base URL:** `<DEPLOYED_BASE_URL>`
- **Health Endpoint:** `<DEPLOYED_BASE_URL>/health`
- **Optimization Endpoint:** `<DEPLOYED_BASE_URL>/optimize-energy`

*(The live endpoint is accessible publicly over HTTPS with no authentication, token, or VPN required.)*

---

## 10. External Libraries and Tools Credited

- **[FastAPI](https://fastapi.tiangolo.com/):** High-performance Python web framework for API routing and lifecycle management.
- **[Uvicorn](https://www.uvicorn.org/):** Lightning-fast ASGI web server implementation.
- **[Pydantic v2](https://docs.pydantic.dev/):** High-performance data validation and settings management.
- **[SciPy](https://scipy.org/):** Numerical computing library providing `scipy.optimize.linprog` with the HiGHS dual-simplex solver.
- **[HTTPX](https://www.python-httpx.org/):** Next-generation HTTP client for structured communication with Google Generative Language APIs.
- **[python-dotenv](https://github.com/theskumar/python-dotenv):** Reads key-value pairs from `.env` files for local development.
- **[pytest](https://docs.pytest.org/):** Robust testing framework for unit and regression verification.
- **[Google Gemini API](https://ai.google.dev/):** Generative language foundation model (`gemini-3.1-flash-lite`) providing structured natural language understanding.

---

## 11. Known Limitations and Documented Assumptions

1. **Overlapping Solar Reductions:** When multiple operator notes specify solar reduction factors affecting the same hour, the directive compiler applies the **minimum** active factor rather than compounding/multiplying them (e.g., reductions of 0.8 and 0.5 resolve to 0.5 effective factor). This ensures conservative generation bounds in line with typical utility curtailment protocols.
2. **Overlapping Battery Reserves:** When multiple notes enforce battery reserve minimums on overlapping hours, the system enforces the **maximum** reserve level (`max(r_1, r_2, ...)`), upholding the safest required reserve buffer.
3. **Overlapping Grid Caps:** When multiple notes enforce grid import caps on the same hour, the system applies the **minimum** cap (`min(cap_1, cap_2, ...)`), satisfying the strictest physical restriction.
4. **End-of-Day Neutrality:** As required by the specification, the final battery storage at the conclusion of Hour 23 must equal the initial energy at the start of Hour 0 (`battery_energy_after_kwh[23] == initial_energy_kwh`).
5. **No Cross-Day Carryover:** The optimization problem is strictly bounded to the 24-hour horizon (Hours 0 through 23).
6. **Contradictory Directives:** If operator notes impose mutually exclusive constraints (e.g., simultaneous bans on charging and discharging while demand cannot be met by available solar and grid caps), the linear program correctly identifies primal infeasibility and returns an appropriate error rather than fabricating an invalid schedule.

---

## 12. Secret-Handling Confirmation

- Real API credentials must never be committed to source code or included in Docker build images.
- Environment variables (`GEMINI_API_KEY`) are passed exclusively at container runtime or stored in a local `.env` file.
- Both `.gitignore` and `.dockerignore` exclude `.env` and `.env.*` to prevent inadvertent credential leakage.
- **Confirmation:** No API keys, credentials, or secrets are contained anywhere in this documentation or committed repository files.
